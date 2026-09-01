from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from bson import ObjectId
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.config import settings
from app.db import db
from app.dependencies import require_org_admin, require_system_admin
from app.main import app
from app.schemas.admin import AdminCreate, AdminResponse
from app.services.admin_auth_service import AdminAuthService
from app.services.admin_session_service import AdminSessionService
from app.services.jwt_service import JWTService
from app.services.organization_service import OrganizationService
from app.services.rate_limiter import auth_rate_limiter

client = TestClient(app)

TEST_ORG_ID = "pec2026-auth"
TEST_ADMIN_EMAIL = "sysadmin@example.com"
TEST_ORG_ADMIN_EMAIL = "orgadmin@example.com"
TEST_PASSWORD = "StrongAdminPass123"


@pytest.fixture(autouse=True)
def cleanup_admin_data():
    auth_rate_limiter.clear()
    db.get_db()["admin_users"].drop()
    db.get_db()["admin_sessions"].drop()
    db.get_db()["organizations"].drop()
    db.get_db()["users"].delete_many({"email": {"$in": ["normaluser@example.com"]}})
    db.ensure_indexes()

    yield

    auth_rate_limiter.clear()
    db.get_db()["admin_users"].drop()
    db.get_db()["admin_sessions"].drop()
    db.get_db()["organizations"].drop()
    db.get_db()["users"].delete_many({"email": {"$in": ["normaluser@example.com"]}})
    db.ensure_indexes()


def create_test_org() -> str:
    org = OrganizationService.create_organization(
        org_id=TEST_ORG_ID,
        name="Panimalar Engineering College",
        join_code="pecsecret123",
    )
    return org["id"]


# ==========================================
# 1. Admin Creation Tests (1-12)
# ==========================================

def test_valid_system_admin_creation():
    payload = AdminCreate(
        email=TEST_ADMIN_EMAIL,
        name="System Administrator",
        password=TEST_PASSWORD,
        role="system_admin",
        organization_id=None,
    )
    admin = AdminAuthService.create_admin(payload)
    assert admin["email"] == TEST_ADMIN_EMAIL
    assert admin["name"] == "System Administrator"
    assert admin["role"] == "system_admin"
    assert admin["organization_id"] is None
    assert admin["is_active"] is True
    assert isinstance(admin["created_at"], datetime)


def test_valid_org_admin_creation():
    org_id = create_test_org()
    payload = AdminCreate(
        email=TEST_ORG_ADMIN_EMAIL,
        name="Org Administrator",
        password=TEST_PASSWORD,
        role="org_admin",
        organization_id=org_id,
    )
    admin = AdminAuthService.create_admin(payload)
    assert admin["email"] == TEST_ORG_ADMIN_EMAIL
    assert admin["role"] == "org_admin"
    assert admin["organization_id"] == org_id


def test_system_admin_with_organization_id_rejected():
    org_id = create_test_org()
    with pytest.raises(Exception):
        AdminCreate(
            email="sysbad@example.com",
            name="Sys Bad",
            password=TEST_PASSWORD,
            role="system_admin",
            organization_id=org_id,
        )


def test_org_admin_without_organization_id_rejected():
    with pytest.raises(Exception):
        AdminCreate(
            email="orgbad@example.com",
            name="Org Bad",
            password=TEST_PASSWORD,
            role="org_admin",
            organization_id=None,
        )


def test_org_admin_with_invalid_object_id_rejected():
    with pytest.raises(Exception):
        AdminCreate(
            email="orgbad2@example.com",
            name="Org Bad",
            password=TEST_PASSWORD,
            role="org_admin",
            organization_id="not-an-object-id",
        )


def test_org_admin_with_nonexistent_organization_rejected():
    fake_org_id = str(ObjectId())
    payload = AdminCreate(
        email="orgnonexistent@example.com",
        name="Org Admin Nonexistent",
        password=TEST_PASSWORD,
        role="org_admin",
        organization_id=fake_org_id,
    )
    with pytest.raises(HTTPException) as exc_info:
        AdminAuthService.create_admin(payload)
    assert exc_info.value.status_code == 404
    assert "Organization not found" in exc_info.value.detail


def test_invalid_role_rejected():
    with pytest.raises(Exception):
        AdminCreate(
            email="invalidrole@example.com",
            name="Invalid Role",
            password=TEST_PASSWORD,
            role="super_user",  # type: ignore
            organization_id=None,
        )


def test_email_normalization():
    payload = AdminCreate(
        email="  SysAdmin_UPPER@Example.COM  ",
        name="Normalized Admin",
        password=TEST_PASSWORD,
        role="system_admin",
        organization_id=None,
    )
    admin = AdminAuthService.create_admin(payload)
    assert admin["email"] == "sysadmin_upper@example.com"


def test_duplicate_admin_email_returns_409():
    payload = AdminCreate(
        email=TEST_ADMIN_EMAIL,
        name="Sys Admin One",
        password=TEST_PASSWORD,
        role="system_admin",
        organization_id=None,
    )
    AdminAuthService.create_admin(payload)

    with pytest.raises(HTTPException) as exc_info:
        AdminAuthService.create_admin(payload)
    assert exc_info.value.status_code == 409
    assert "Admin email already registered" in exc_info.value.detail


def test_password_is_bcrypt_hashed():
    payload = AdminCreate(
        email=TEST_ADMIN_EMAIL,
        name="Sys Admin",
        password=TEST_PASSWORD,
        role="system_admin",
        organization_id=None,
    )
    AdminAuthService.create_admin(payload)
    doc = db.get_db()["admin_users"].find_one({"email": TEST_ADMIN_EMAIL})
    assert doc is not None
    assert doc["password_hash"].startswith(("$2b$", "$2a$"))


def test_raw_password_is_not_stored():
    payload = AdminCreate(
        email=TEST_ADMIN_EMAIL,
        name="Sys Admin",
        password=TEST_PASSWORD,
        role="system_admin",
        organization_id=None,
    )
    AdminAuthService.create_admin(payload)
    doc = db.get_db()["admin_users"].find_one({"email": TEST_ADMIN_EMAIL})
    assert doc is not None
    assert "password" not in doc
    assert TEST_PASSWORD not in doc.values()


def test_admin_response_does_not_expose_password_hash():
    payload = AdminCreate(
        email=TEST_ADMIN_EMAIL,
        name="Sys Admin",
        password=TEST_PASSWORD,
        role="system_admin",
        organization_id=None,
    )
    admin = AdminAuthService.create_admin(payload)
    response_obj = AdminResponse(**admin)
    dumped = response_obj.model_dump()
    assert "password" not in dumped
    assert "password_hash" not in dumped


# ==========================================
# 2. Authentication & Login Tests (13-20)
# ==========================================

def test_successful_admin_login():
    payload = AdminCreate(
        email=TEST_ADMIN_EMAIL,
        name="Sys Admin",
        password=TEST_PASSWORD,
        role="system_admin",
        organization_id=None,
    )
    AdminAuthService.create_admin(payload)

    response = client.post(
        "/admin/auth/login",
        json={"email": TEST_ADMIN_EMAIL, "password": TEST_PASSWORD},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["admin"]["email"] == TEST_ADMIN_EMAIL
    assert data["admin"]["role"] == "system_admin"


def test_incorrect_password_returns_401():
    payload = AdminCreate(
        email=TEST_ADMIN_EMAIL,
        name="Sys Admin",
        password=TEST_PASSWORD,
        role="system_admin",
        organization_id=None,
    )
    AdminAuthService.create_admin(payload)

    response = client.post(
        "/admin/auth/login",
        json={"email": TEST_ADMIN_EMAIL, "password": "WrongPassword123"},
    )
    assert response.status_code == 401
    assert "Invalid email or password" in response.json()["detail"]


def test_unknown_email_returns_401():
    response = client.post(
        "/admin/auth/login",
        json={"email": "unknown@example.com", "password": TEST_PASSWORD},
    )
    assert response.status_code == 401
    assert "Invalid email or password" in response.json()["detail"]


def test_inactive_admin_returns_401():
    payload = AdminCreate(
        email=TEST_ADMIN_EMAIL,
        name="Sys Admin",
        password=TEST_PASSWORD,
        role="system_admin",
        organization_id=None,
    )
    admin = AdminAuthService.create_admin(payload)
    db.get_db()["admin_users"].update_one(
        {"_id": ObjectId(admin["id"])},
        {"$set": {"is_active": False}},
    )

    response = client.post(
        "/admin/auth/login",
        json={"email": TEST_ADMIN_EMAIL, "password": TEST_PASSWORD},
    )
    assert response.status_code == 401
    assert "Invalid email or password" in response.json()["detail"]


def test_login_creates_admin_refresh_cookie():
    payload = AdminCreate(
        email=TEST_ADMIN_EMAIL,
        name="Sys Admin",
        password=TEST_PASSWORD,
        role="system_admin",
        organization_id=None,
    )
    AdminAuthService.create_admin(payload)

    response = client.post(
        "/admin/auth/login",
        json={"email": TEST_ADMIN_EMAIL, "password": TEST_PASSWORD},
    )
    assert response.status_code == 200
    assert "admin_refresh_token" in response.cookies


def test_cookie_is_httponly():
    payload = AdminCreate(
        email=TEST_ADMIN_EMAIL,
        name="Sys Admin",
        password=TEST_PASSWORD,
        role="system_admin",
        organization_id=None,
    )
    AdminAuthService.create_admin(payload)

    response = client.post(
        "/admin/auth/login",
        json={"email": TEST_ADMIN_EMAIL, "password": TEST_PASSWORD},
    )
    cookie_header = response.headers.get("set-cookie", "")
    assert "HttpOnly" in cookie_header or "httponly" in cookie_header


def test_cookie_path_is_admin():
    payload = AdminCreate(
        email=TEST_ADMIN_EMAIL,
        name="Sys Admin",
        password=TEST_PASSWORD,
        role="system_admin",
        organization_id=None,
    )
    AdminAuthService.create_admin(payload)

    response = client.post(
        "/admin/auth/login",
        json={"email": TEST_ADMIN_EMAIL, "password": TEST_PASSWORD},
    )
    cookie_header = response.headers.get("set-cookie", "")
    assert "path=/admin" in cookie_header.lower()


def test_cookie_name_is_admin_refresh_token():
    payload = AdminCreate(
        email=TEST_ADMIN_EMAIL,
        name="Sys Admin",
        password=TEST_PASSWORD,
        role="system_admin",
        organization_id=None,
    )
    AdminAuthService.create_admin(payload)

    response = client.post(
        "/admin/auth/login",
        json={"email": TEST_ADMIN_EMAIL, "password": TEST_PASSWORD},
    )
    cookie_header = response.headers.get("set-cookie", "")
    assert cookie_header.startswith("admin_refresh_token=")


# ==========================================
# 3. Sessions & Rotation Tests (21-31)
# ==========================================

def test_raw_refresh_token_is_never_stored():
    payload = AdminCreate(
        email=TEST_ADMIN_EMAIL,
        name="Sys Admin",
        password=TEST_PASSWORD,
        role="system_admin",
        organization_id=None,
    )
    admin = AdminAuthService.create_admin(payload)
    session_id, raw_token = AdminSessionService.create_session(admin["id"])

    doc = db.get_db()["admin_sessions"].find_one({"_id": ObjectId(session_id)})
    assert doc is not None
    assert "token" not in doc
    assert raw_token not in doc.values()


def test_stored_value_is_sha256_hash():
    payload = AdminCreate(
        email=TEST_ADMIN_EMAIL,
        name="Sys Admin",
        password=TEST_PASSWORD,
        role="system_admin",
        organization_id=None,
    )
    admin = AdminAuthService.create_admin(payload)
    session_id, raw_token = AdminSessionService.create_session(admin["id"])

    doc = db.get_db()["admin_sessions"].find_one({"_id": ObjectId(session_id)})
    assert doc is not None
    expected_hash = AdminSessionService._hash_token(raw_token)
    assert doc["token_hash"] == expected_hash


def test_valid_refresh_works():
    payload = AdminCreate(
        email=TEST_ADMIN_EMAIL,
        name="Sys Admin",
        password=TEST_PASSWORD,
        role="system_admin",
        organization_id=None,
    )
    AdminAuthService.create_admin(payload)

    login_res = client.post(
        "/admin/auth/login",
        json={"email": TEST_ADMIN_EMAIL, "password": TEST_PASSWORD},
    )
    cookie_val = login_res.cookies.get("admin_refresh_token")

    refresh_res = client.post(
        "/admin/auth/refresh",
        cookies={"admin_refresh_token": cookie_val},
    )
    assert refresh_res.status_code == 200
    assert "access_token" in refresh_res.json()
    assert "admin_refresh_token" in refresh_res.cookies


def test_refresh_rotates_token():
    payload = AdminCreate(
        email=TEST_ADMIN_EMAIL,
        name="Sys Admin",
        password=TEST_PASSWORD,
        role="system_admin",
        organization_id=None,
    )
    AdminAuthService.create_admin(payload)

    login_res = client.post(
        "/admin/auth/login",
        json={"email": TEST_ADMIN_EMAIL, "password": TEST_PASSWORD},
    )
    old_cookie = login_res.cookies.get("admin_refresh_token")

    refresh_res = client.post(
        "/admin/auth/refresh",
        cookies={"admin_refresh_token": old_cookie},
    )
    new_cookie = refresh_res.cookies.get("admin_refresh_token")
    assert new_cookie is not None
    assert new_cookie != old_cookie


def test_old_refresh_token_fails_after_rotation():
    payload = AdminCreate(
        email=TEST_ADMIN_EMAIL,
        name="Sys Admin",
        password=TEST_PASSWORD,
        role="system_admin",
        organization_id=None,
    )
    AdminAuthService.create_admin(payload)

    login_res = client.post(
        "/admin/auth/login",
        json={"email": TEST_ADMIN_EMAIL, "password": TEST_PASSWORD},
    )
    old_cookie = login_res.cookies.get("admin_refresh_token")

    # Rotate once
    client.post(
        "/admin/auth/refresh",
        cookies={"admin_refresh_token": old_cookie},
    )

    # Attempt replay with old cookie
    replay_res = client.post(
        "/admin/auth/refresh",
        cookies={"admin_refresh_token": old_cookie},
    )
    assert replay_res.status_code == 401


def test_expired_session_fails():
    payload = AdminCreate(
        email=TEST_ADMIN_EMAIL,
        name="Sys Admin",
        password=TEST_PASSWORD,
        role="system_admin",
        organization_id=None,
    )
    admin = AdminAuthService.create_admin(payload)
    session_id, raw_token = AdminSessionService.create_session(admin["id"])

    # Manually expire the session
    db.get_db()["admin_sessions"].update_one(
        {"_id": ObjectId(session_id)},
        {"$set": {"expires_at": datetime.now(timezone.utc) - timedelta(days=1)}},
    )

    with pytest.raises(HTTPException) as exc_info:
        AdminSessionService.validate_session(session_id, raw_token)
    assert exc_info.value.status_code == 401


def test_revoked_session_fails():
    payload = AdminCreate(
        email=TEST_ADMIN_EMAIL,
        name="Sys Admin",
        password=TEST_PASSWORD,
        role="system_admin",
        organization_id=None,
    )
    admin = AdminAuthService.create_admin(payload)
    session_id, raw_token = AdminSessionService.create_session(admin["id"])

    AdminSessionService.revoke_session(session_id)

    with pytest.raises(HTTPException) as exc_info:
        AdminSessionService.validate_session(session_id, raw_token)
    assert exc_info.value.status_code == 401


def test_logout_revokes_session():
    payload = AdminCreate(
        email=TEST_ADMIN_EMAIL,
        name="Sys Admin",
        password=TEST_PASSWORD,
        role="system_admin",
        organization_id=None,
    )
    AdminAuthService.create_admin(payload)

    login_res = client.post(
        "/admin/auth/login",
        json={"email": TEST_ADMIN_EMAIL, "password": TEST_PASSWORD},
    )
    cookie_val = login_res.cookies.get("admin_refresh_token")
    session_id = cookie_val.split(".")[0]

    logout_res = client.post(
        "/admin/auth/logout",
        cookies={"admin_refresh_token": cookie_val},
    )
    assert logout_res.status_code == 200

    doc = db.get_db()["admin_sessions"].find_one({"_id": ObjectId(session_id)})
    assert doc is not None
    assert doc["revoked_at"] is not None


def test_logout_clears_cookie():
    payload = AdminCreate(
        email=TEST_ADMIN_EMAIL,
        name="Sys Admin",
        password=TEST_PASSWORD,
        role="system_admin",
        organization_id=None,
    )
    AdminAuthService.create_admin(payload)

    login_res = client.post(
        "/admin/auth/login",
        json={"email": TEST_ADMIN_EMAIL, "password": TEST_PASSWORD},
    )
    cookie_val = login_res.cookies.get("admin_refresh_token")

    logout_res = client.post(
        "/admin/auth/logout",
        cookies={"admin_refresh_token": cookie_val},
    )
    set_cookie = logout_res.headers.get("set-cookie", "")
    assert "admin_refresh_token" in set_cookie
    assert 'max-age=0' in set_cookie.lower() or 'expires=' in set_cookie.lower()


def test_deactivated_admin_cannot_refresh():
    payload = AdminCreate(
        email=TEST_ADMIN_EMAIL,
        name="Sys Admin",
        password=TEST_PASSWORD,
        role="system_admin",
        organization_id=None,
    )
    admin = AdminAuthService.create_admin(payload)

    login_res = client.post(
        "/admin/auth/login",
        json={"email": TEST_ADMIN_EMAIL, "password": TEST_PASSWORD},
    )
    cookie_val = login_res.cookies.get("admin_refresh_token")

    # Deactivate admin
    db.get_db()["admin_users"].update_one(
        {"_id": ObjectId(admin["id"])},
        {"$set": {"is_active": False}},
    )

    refresh_res = client.post(
        "/admin/auth/refresh",
        cookies={"admin_refresh_token": cookie_val},
    )
    assert refresh_res.status_code == 401


def test_revoked_admin_session_cannot_refresh():
    payload = AdminCreate(
        email=TEST_ADMIN_EMAIL,
        name="Sys Admin",
        password=TEST_PASSWORD,
        role="system_admin",
        organization_id=None,
    )
    AdminAuthService.create_admin(payload)

    login_res = client.post(
        "/admin/auth/login",
        json={"email": TEST_ADMIN_EMAIL, "password": TEST_PASSWORD},
    )
    cookie_val = login_res.cookies.get("admin_refresh_token")

    # Logout
    client.post("/admin/auth/logout", cookies={"admin_refresh_token": cookie_val})

    # Try refresh
    refresh_res = client.post(
        "/admin/auth/refresh",
        cookies={"admin_refresh_token": cookie_val},
    )
    assert refresh_res.status_code == 401


# ==========================================
# 4. Rate Limiting Tests (32)
# ==========================================

def test_admin_login_rate_limit_returns_429():
    for _ in range(settings.AUTH_RATE_LIMIT_REQUESTS):
        client.post(
            "/admin/auth/login",
            json={"email": "ratelimit@example.com", "password": "wrongpassword"},
        )

    # Exceeding request
    response = client.post(
        "/admin/auth/login",
        json={"email": "ratelimit@example.com", "password": "wrongpassword"},
    )
    assert response.status_code == 429
    assert "Too many authentication requests" in response.json()["detail"]
    assert "Retry-After" in response.headers


# ==========================================
# 5. Token & Cross-Boundary Isolation Tests (33-38)
# ==========================================

def test_normal_user_jwt_cannot_access_admin_me():
    # Register and verify a normal user
    client.post(
        "/auth/register",
        json={"name": "Normal User", "email": "normaluser@example.com", "password": "UserPassword123"},
    )
    client.post("/auth/register/verify", json={"email": "normaluser@example.com", "otp": "123456"})
    client.post("/auth/login", json={"email": "normaluser@example.com", "password": "UserPassword123"})
    user_token = client.post("/auth/login/verify", json={"email": "normaluser@example.com", "otp": "123456"}).json()["access_token"]

    response = client.get(
        "/admin/auth/me",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert response.status_code == 401


def test_admin_jwt_cannot_access_user_me():
    payload = AdminCreate(
        email=TEST_ADMIN_EMAIL,
        name="Sys Admin",
        password=TEST_PASSWORD,
        role="system_admin",
        organization_id=None,
    )
    AdminAuthService.create_admin(payload)
    login_res = client.post(
        "/admin/auth/login",
        json={"email": TEST_ADMIN_EMAIL, "password": TEST_PASSWORD},
    )
    admin_token = login_res.json()["access_token"]

    response = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 401


def test_forged_jwt_without_type_admin_cannot_access_admin_endpoint():
    token = JWTService.create_access_token("some_admin_id")
    response = client.get(
        "/admin/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401


def test_admin_jwt_with_wrong_type_cannot_access_admin_endpoint():
    payload = {
        "sub": str(ObjectId()),
        "type": "guest",
        "iat": int(datetime.now(timezone.utc).timestamp()),
        "exp": int((datetime.now(timezone.utc) + timedelta(minutes=30)).timestamp()),
    }
    import jwt
    token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

    response = client.get(
        "/admin/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401


def test_normal_refresh_token_cannot_refresh_admin_session():
    # Login normal user
    client.post(
        "/auth/register",
        json={"name": "Normal User", "email": "normaluser@example.com", "password": "UserPassword123"},
    )
    client.post("/auth/register/verify", json={"email": "normaluser@example.com", "otp": "123456"})
    client.post("/auth/login", json={"email": "normaluser@example.com", "password": "UserPassword123"})
    login_res = client.post("/auth/login/verify", json={"email": "normaluser@example.com", "otp": "123456"})
    user_cookie = login_res.cookies.get("refresh_token")

    # Send user cookie to admin refresh endpoint
    response = client.post(
        "/admin/auth/refresh",
        cookies={"admin_refresh_token": user_cookie},
    )
    assert response.status_code == 401


def test_admin_refresh_token_cannot_refresh_normal_user_session():
    payload = AdminCreate(
        email=TEST_ADMIN_EMAIL,
        name="Sys Admin",
        password=TEST_PASSWORD,
        role="system_admin",
        organization_id=None,
    )
    AdminAuthService.create_admin(payload)
    login_res = client.post(
        "/admin/auth/login",
        json={"email": TEST_ADMIN_EMAIL, "password": TEST_PASSWORD},
    )
    admin_cookie = login_res.cookies.get("admin_refresh_token")

    # Send admin cookie to normal user refresh endpoint
    response = client.post(
        "/auth/refresh",
        cookies={"refresh_token": admin_cookie},
    )
    assert response.status_code == 401


# ==========================================
# 6. Role Authorization Tests (39-41)
# ==========================================

def test_system_admin_passes_require_system_admin():
    admin = {"role": "system_admin", "name": "Sys Admin"}
    assert require_system_admin(admin) == admin


def test_org_admin_is_rejected_by_require_system_admin():
    admin = {"role": "org_admin", "name": "Org Admin"}
    with pytest.raises(HTTPException) as exc_info:
        require_system_admin(admin)
    assert exc_info.value.status_code == 403
    assert "System administrator access required" in exc_info.value.detail


def test_org_admin_passes_require_org_admin():
    admin = {"role": "org_admin", "name": "Org Admin"}
    assert require_org_admin(admin) == admin


# ==========================================
# 7. Database Indexes Tests (42-45)
# ==========================================

def test_admin_email_index_is_unique():
    indexes = db.get_db()["admin_users"].list_indexes()
    idx = next((i for i in indexes if i["name"] == "admin_users_email_unique_idx"), None)
    assert idx is not None
    assert idx["key"] == {"email": 1}
    assert idx["unique"] is True


def test_admin_session_token_hash_index_is_unique():
    indexes = db.get_db()["admin_sessions"].list_indexes()
    idx = next((i for i in indexes if i["name"] == "admin_sessions_token_hash_unique_idx"), None)
    assert idx is not None
    assert idx["key"] == {"token_hash": 1}
    assert idx["unique"] is True


def test_admin_session_expiration_index_is_ttl():
    indexes = db.get_db()["admin_sessions"].list_indexes()
    idx = next((i for i in indexes if i["name"] == "admin_sessions_expires_ttl_idx"), None)
    assert idx is not None
    assert idx["key"] == {"expires_at": 1}
    assert idx.get("expireAfterSeconds") == 0


def test_ready_reports_admin_indexes_correctly():
    db.ensure_indexes()
    response = client.get("/ready")
    assert response.status_code == 200
    res_json = response.json()
    assert res_json["ready"] is True

    indexes_info = res_json["indexes"]
    assert "admin_users" in indexes_info
    assert "admin_users_email_unique_idx" in indexes_info["admin_users"]["present"]

    assert "admin_sessions" in indexes_info
    assert "admin_sessions_token_hash_unique_idx" in indexes_info["admin_sessions"]["present"]
    assert "admin_sessions_expires_ttl_idx" in indexes_info["admin_sessions"]["present"]
