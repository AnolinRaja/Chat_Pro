import pytest
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from bson import ObjectId

from app.config import settings
from app.db import db
from app.main import app
from app.services.session_service import SessionService
from app.services.auth_service import AuthService

client = TestClient(app)

TEST_EMAIL = "sessiontest@example.com"
TEST_PASSWORD = "TestPassword123"


@pytest.fixture(autouse=True)
def cleanup_test_user():
    collection = db.get_db()["users"]
    collection.delete_many({"email": TEST_EMAIL})
    
    # Drop collection to clear stale database indexes
    db.get_db()["auth_sessions"].drop()
    # Recreate the correct expected indexes
    db.ensure_indexes()
    
    yield
    
    collection.delete_many({"email": TEST_EMAIL})
    db.get_db()["auth_sessions"].drop()


def register_and_verify_user():
    client.post("/auth/register", json={"name": "Session User", "email": TEST_EMAIL, "password": TEST_PASSWORD})
    client.post("/auth/register/verify", json={"email": TEST_EMAIL, "otp": "123456"})
    user = db.get_db()["users"].find_one({"email": TEST_EMAIL})
    return str(user["_id"])


def test_session_creation_service():
    user_id = register_and_verify_user()
    session_id, raw_token = SessionService.create_session(user_id)
    
    assert session_id is not None
    assert raw_token is not None
    
    # Verify stored in DB
    session = db.get_db()["auth_sessions"].find_one({"_id": ObjectId(session_id)})
    assert session is not None
    assert session["user_id"] == ObjectId(user_id)
    assert session["token_hash"] == SessionService._hash_token(raw_token)
    assert session["revoked_at"] is None
    
    expires_at = session["expires_at"]
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    assert expires_at > datetime.now(timezone.utc)


def test_validate_and_refresh_session_success():
    user_id = register_and_verify_user()
    session_id, raw_token = SessionService.create_session(user_id)
    
    # Validate session
    validated_user_id = SessionService.validate_session(session_id, raw_token)
    assert validated_user_id == user_id


def test_validate_session_expired():
    user_id = register_and_verify_user()
    session_id, raw_token = SessionService.create_session(user_id)
    
    # Artificially expire the session
    db.get_db()["auth_sessions"].update_one(
        {"_id": ObjectId(session_id)},
        {"$set": {"expires_at": datetime.now(timezone.utc) - timedelta(seconds=1)}}
    )
    
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        SessionService.validate_session(session_id, raw_token)
    assert exc.value.status_code == 401


def test_validate_session_revoked():
    user_id = register_and_verify_user()
    session_id, raw_token = SessionService.create_session(user_id)
    
    SessionService.revoke_session(session_id)
    
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        SessionService.validate_session(session_id, raw_token)
    assert exc.value.status_code == 401


def test_rotate_refresh_token():
    user_id = register_and_verify_user()
    session_id, raw_token = SessionService.create_session(user_id)
    
    # Rotate
    new_session_id, new_raw_token, rotated_user_id = SessionService.rotate_refresh_token(session_id, raw_token)
    assert new_session_id == session_id
    assert new_raw_token != raw_token
    assert rotated_user_id == user_id
    
    # Old token should fail validation now
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        SessionService.validate_session(session_id, raw_token)
    assert exc.value.status_code == 401
    
    # New token should succeed validation
    assert SessionService.validate_session(session_id, new_raw_token) == user_id


def test_revoke_all_user_sessions():
    user_id = register_and_verify_user()
    s1, t1 = SessionService.create_session(user_id)
    s2, t2 = SessionService.create_session(user_id)
    
    # Revoke all
    SessionService.revoke_all_user_sessions(user_id)
    
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        SessionService.validate_session(s1, t1)
    with pytest.raises(HTTPException):
        SessionService.validate_session(s2, t2)


def test_multiple_sessions_independent():
    user_id = register_and_verify_user()
    s1, t1 = SessionService.create_session(user_id)
    s2, t2 = SessionService.create_session(user_id)
    
    # Revoke session 1
    SessionService.revoke_session(s1)
    
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        SessionService.validate_session(s1, t1)
        
    # Session 2 should still be valid
    assert SessionService.validate_session(s2, t2) == user_id


def test_login_verify_creates_session_cookie():
    register_and_verify_user()
    
    # OTP is mock OTP "123456" in non-test_otp_service.py test runs due to conftest.py
    client.post("/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
    response = client.post("/auth/login/verify", json={"email": TEST_EMAIL, "otp": "123456"})
    
    assert response.status_code == 200
    assert "access_token" in response.json()
    assert "refresh_token" not in response.json()  # Refresh token must NOT be in JSON response!
    
    # Check refresh_token cookie
    cookies = response.cookies
    assert "refresh_token" in cookies
    cookie_val = cookies["refresh_token"]
    assert "." in cookie_val
    
    session_id, raw_token = cookie_val.split(".", 1)
    assert session_id is not None
    assert raw_token is not None


def test_refresh_endpoint_success():
    register_and_verify_user()
    
    client.post("/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
    res_login = client.post("/auth/login/verify", json={"email": TEST_EMAIL, "otp": "123456"})
    
    # Refresh
    client.cookies.set("refresh_token", res_login.cookies["refresh_token"])
    response = client.post("/auth/refresh")
    
    assert response.status_code == 200
    assert "access_token" in response.json()
    assert "refresh_token" not in response.json()
    
    # Assert cookie is rotated
    assert response.cookies["refresh_token"] != res_login.cookies["refresh_token"]


def test_logout_endpoint_success():
    register_and_verify_user()
    
    client.post("/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
    res_login = client.post("/auth/login/verify", json={"email": TEST_EMAIL, "otp": "123456"})
    
    # Logout
    client.cookies.clear()
    client.cookies.set("refresh_token", res_login.cookies["refresh_token"])
    response = client.post("/auth/logout")
    
    assert response.status_code == 200
    
    # Check cookie is deleted
    cookie = response.cookies.get("refresh_token")
    assert cookie is None or cookie == ""
    
    # Check that session is revoked in DB
    session_id, _ = res_login.cookies["refresh_token"].split(".", 1)
    session = db.get_db()["auth_sessions"].find_one({"_id": ObjectId(session_id)})
    assert session["revoked_at"] is not None
