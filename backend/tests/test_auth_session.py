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
    
    response = client.post("/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
    
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
    
    res_login = client.post("/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
    
    # Refresh
    client.cookies.set("refresh_token", res_login.cookies["refresh_token"])
    response = client.post("/auth/refresh")
    
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" not in data
    assert "user" in data
    assert data["user"]["email"] == TEST_EMAIL
    assert data["user"]["name"] == "Session User"
    assert "two_factor_enabled" in data["user"]
    # Ensure NO sensitive fields are leaked
    assert "password_hash" not in data["user"]
    assert "two_factor_secret" not in data["user"]
    assert "recovery_codes_hash" not in data["user"]
    
    # Assert cookie is rotated
    assert response.cookies["refresh_token"] != res_login.cookies["refresh_token"]


def test_logout_endpoint_success():
    register_and_verify_user()
    
    res_login = client.post("/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
    
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


def test_refresh_without_cookie_fails_401():
    client.cookies.clear()
    response = client.post("/auth/refresh")
    assert response.status_code == 401
    assert "Invalid or expired session" in response.json()["detail"]


def test_refresh_with_malformed_cookie_fails_401():
    client.cookies.set("refresh_token", "invalid_cookie_format")
    response = client.post("/auth/refresh")
    assert response.status_code == 401
    assert "Invalid or expired session" in response.json()["detail"]


def test_refresh_with_expired_session_fails_401():
    user_id = register_and_verify_user()
    session_id, raw_token = SessionService.create_session(user_id)

    # Expire session in DB
    db.get_db()["auth_sessions"].update_one(
        {"_id": ObjectId(session_id)},
        {"$set": {"expires_at": datetime.now(timezone.utc) - timedelta(seconds=1)}}
    )

    client.cookies.set("refresh_token", f"{session_id}.{raw_token}")
    response = client.post("/auth/refresh")
    assert response.status_code == 401
    assert "Invalid or expired session" in response.json()["detail"]


def test_refresh_with_revoked_session_fails_401():
    user_id = register_and_verify_user()
    session_id, raw_token = SessionService.create_session(user_id)
    SessionService.revoke_session(session_id)

    client.cookies.set("refresh_token", f"{session_id}.{raw_token}")
    response = client.post("/auth/refresh")
    assert response.status_code == 401
    assert "Invalid or expired session" in response.json()["detail"]


def test_startup_session_restoration_lifecycle():
    """Simulates startup session restoration via HttpOnly cookie returning token + sanitized user in single roundtrip."""
    register_and_verify_user()

    # User logs in and receives refresh_token cookie
    login_res = client.post("/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
    assert login_res.status_code == 200
    cookie = login_res.cookies["refresh_token"]

    # Clear memory / client state, simulating fresh browser/PWA launch
    client.cookies.clear()
    client.cookies.set("refresh_token", cookie)

    # App startup calls /auth/refresh — returns access token AND sanitized user profile directly
    refresh_res = client.post("/auth/refresh")
    assert refresh_res.status_code == 200
    refresh_data = refresh_res.json()
    new_access_token = refresh_data["access_token"]
    assert new_access_token is not None
    assert refresh_data["user"] is not None
    assert refresh_data["user"]["email"] == TEST_EMAIL
    assert refresh_data["user"]["name"] == "Session User"

    # Optional /auth/me backward-compatible verification
    me_res = client.get("/auth/me", headers={"Authorization": f"Bearer {new_access_token}"})
    assert me_res.status_code == 200
    me_data = me_res.json()
    assert me_data["email"] == TEST_EMAIL


def test_2sv_challenge_token_cannot_access_refresh_or_me():
    """Verify that an intermediate 2SV challenge token cannot be used at /auth/refresh or /auth/me."""
    from app.services.jwt_service import JWTService

    user_id = register_and_verify_user()

    # Issue an intermediate 2sv challenge token
    challenge_token = JWTService.create_auth_challenge(user_id, "2sv_login")

    # 1. Challenge token in Authorization header at /auth/me must fail with 401
    me_res = client.get("/auth/me", headers={"Authorization": f"Bearer {challenge_token}"})
    assert me_res.status_code == 401

    # 2. Challenge token set as cookie at /auth/refresh must fail with 401
    client.cookies.set("refresh_token", challenge_token)
    refresh_res = client.post("/auth/refresh")
    assert refresh_res.status_code == 401


def test_password_reset_revokes_all_prior_sessions():
    """Verify that completing a password reset revokes all existing sessions."""
    user_id = register_and_verify_user()
    s1, t1 = SessionService.create_session(user_id)
    s2, t2 = SessionService.create_session(user_id)

    # Request and complete password reset
    client.post("/auth/forgot-password/request", json={"email": TEST_EMAIL})
    verify_res = client.post("/auth/forgot-password/verify", json={"email": TEST_EMAIL, "otp": "123456"})
    reset_token = verify_res.json()["reset_token"]

    reset_res = client.post("/auth/forgot-password/reset", json={"reset_token": reset_token, "new_password": "NewTestPassword456!"})
    assert reset_res.status_code == 200

    # Both sessions must now be revoked
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        SessionService.validate_session(s1, t1)
    with pytest.raises(HTTPException):
        SessionService.validate_session(s2, t2)


def test_deleted_or_nonexistent_user_cannot_refresh():
    """Verify that a session for a nonexistent user fails refresh with 401."""
    user_id = register_and_verify_user()
    session_id, raw_token = SessionService.create_session(user_id)

    # Delete the user from DB
    db.get_db()["users"].delete_one({"_id": ObjectId(user_id)})

    client.cookies.set("refresh_token", f"{session_id}.{raw_token}")
    response = client.post("/auth/refresh")
    assert response.status_code == 401


def test_unverified_user_cannot_refresh():
    """Verify that an unverified user cannot refresh session."""
    user_id = register_and_verify_user()
    session_id, raw_token = SessionService.create_session(user_id)

    # Mark user as not verified
    db.get_db()["users"].update_one({"_id": ObjectId(user_id)}, {"$set": {"email_verified": False}})

    client.cookies.set("refresh_token", f"{session_id}.{raw_token}")
    response = client.post("/auth/refresh")
    assert response.status_code == 401


def test_2sv_enable_and_disable_revokes_prior_sessions_and_creates_fresh():
    """Verify that enabling/disabling 2SV revokes prior sessions and issues a new session cookie."""
    import pyotp
    from app.services.two_factor_service import TwoFactorService
    from app.services.jwt_service import JWTService

    user_id = register_and_verify_user()
    s1, t1 = SessionService.create_session(user_id)

    # 1. Setup 2SV
    setup_res = TwoFactorService.setup_2sv(user_id, TEST_EMAIL)
    secret = setup_res["secret"]
    valid_code = pyotp.TOTP(secret).now()

    # Issue auth token for user to call /2sv/confirm
    auth_token = JWTService.create_access_token(user_id)

    # Confirm 2SV
    confirm_res = client.post(
        "/auth/2sv/confirm",
        json={"code": valid_code},
        headers={"Authorization": f"Bearer {auth_token}"}
    )
    assert confirm_res.status_code == 200
    assert "refresh_token" in confirm_res.cookies

    # Prior session s1 must be revoked
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        SessionService.validate_session(s1, t1)

    # New session cookie from confirm must be valid
    new_cookie = confirm_res.cookies["refresh_token"]
    new_s_id, new_raw_token = new_cookie.split(".", 1)
    assert SessionService.validate_session(new_s_id, new_raw_token) == user_id

    # 2. Disable 2SV
    disable_code = pyotp.TOTP(secret).now()
    disable_res = client.post(
        "/auth/2sv/disable",
        json={"password": TEST_PASSWORD, "code": disable_code},
        headers={"Authorization": f"Bearer {auth_token}"}
    )
    assert disable_res.status_code == 200
    assert "refresh_token" in disable_res.cookies

    # The session from confirm (new_s_id) must now be revoked
    with pytest.raises(HTTPException):
        SessionService.validate_session(new_s_id, new_raw_token)

    # Fresh session from disable must be valid
    disabled_cookie = disable_res.cookies["refresh_token"]
    disabled_s_id, disabled_raw_token = disabled_cookie.split(".", 1)
    assert SessionService.validate_session(disabled_s_id, disabled_raw_token) == user_id
