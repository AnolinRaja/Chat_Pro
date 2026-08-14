import jwt
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.db import db
from app.main import app

client = TestClient(app)

TEST_EMAIL = "test@example.com"
TEST_PASSWORD = "TestPassword123"


@pytest.fixture(autouse=True)
def cleanup_test_user():
    collection = db.get_db()["users"]
    collection.delete_many({"email": {"$in": [TEST_EMAIL, "testupper@example.com"]}})
    yield
    collection.delete_many({"email": {"$in": [TEST_EMAIL, "testupper@example.com"]}})


def register_user(payload):
    return client.post("/auth/register", json=payload)


def test_successful_login_returns_token():
    register_user({"name": "Test User", "email": TEST_EMAIL, "password": TEST_PASSWORD})

    response = client.post("/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})

    assert response.status_code == 200
    body = response.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"
    assert "password" not in body
    assert "password_hash" not in body


def test_login_token_type_is_bearer():
    register_user({"name": "Test User", "email": TEST_EMAIL, "password": TEST_PASSWORD})
    response = client.post("/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})

    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"


def test_login_token_can_be_decoded():
    register_user({"name": "Test User", "email": TEST_EMAIL, "password": TEST_PASSWORD})
    token = client.post("/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD}).json()["access_token"]

    payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    assert "sub" in payload
    assert "exp" in payload


def test_login_token_sub_matches_user_id():
    register_user({"name": "Test User", "email": TEST_EMAIL, "password": TEST_PASSWORD})
    user = db.get_db()["users"].find_one({"email": TEST_EMAIL})
    token = client.post("/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD}).json()["access_token"]

    payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    assert payload["sub"] == str(user["_id"])


def test_wrong_password_returns_401():
    register_user({"name": "Test User", "email": TEST_EMAIL, "password": TEST_PASSWORD})

    response = client.post("/auth/login", json={"email": TEST_EMAIL, "password": "WrongPassword123"})

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password."


def test_nonexistent_email_returns_401():
    response = client.post("/auth/login", json={"email": "missing@example.com", "password": TEST_PASSWORD})

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password."


def test_login_email_normalization():
    register_user({"name": "Test User", "email": TEST_EMAIL, "password": TEST_PASSWORD})

    response = client.post("/auth/login", json={"email": "TEST@EXAMPLE.COM", "password": TEST_PASSWORD})

    assert response.status_code == 200


def test_login_missing_email_validation():
    response = client.post("/auth/login", json={"password": TEST_PASSWORD})
    assert response.status_code == 422


def test_login_invalid_email_format():
    response = client.post("/auth/login", json={"email": "bad-email", "password": TEST_PASSWORD})
    assert response.status_code == 422


def test_login_missing_password_validation():
    response = client.post("/auth/login", json={"email": TEST_EMAIL})
    assert response.status_code == 422


def test_expired_token_is_rejected():
    register_user({"name": "Test User", "email": TEST_EMAIL, "password": TEST_PASSWORD})
    user = db.get_db()["users"].find_one({"email": TEST_EMAIL})

    expired_token = jwt.encode({"sub": str(user["_id"]), "exp": 1}, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    response = client.get("/auth/me", headers={"Authorization": f"Bearer {expired_token}"})

    assert response.status_code == 401


def test_invalid_token_is_rejected():
    response = client.get("/auth/me", headers={"Authorization": "Bearer not-a-valid-jwt"})
    assert response.status_code == 401


def test_wrong_signature_is_rejected():
    register_user({"name": "Test User", "email": TEST_EMAIL, "password": TEST_PASSWORD})
    user = db.get_db()["users"].find_one({"email": TEST_EMAIL})

    wrong_token = jwt.encode(
    {"sub": str(user["_id"]), "exp": 9999999999},
    "definitely-wrong-secret-for-testing-only-123456789",
    algorithm=settings.JWT_ALGORITHM
)
    response = client.get("/auth/me", headers={"Authorization": f"Bearer {wrong_token}"})

    assert response.status_code == 401


def test_missing_authorization_header_is_rejected():
    response = client.get("/auth/me")
    assert response.status_code == 401


def test_invalid_authorization_scheme_is_rejected():
    response = client.get("/auth/me", headers={"Authorization": "Basic something"})
    assert response.status_code == 401


def test_login_response_does_not_expose_passwords():
    register_user({"name": "Test User", "email": TEST_EMAIL, "password": TEST_PASSWORD})
    response = client.post("/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})

    payload = response.json()
    assert "password" not in payload
    assert "password_hash" not in payload


def test_auth_me_returns_current_user_without_sensitive_data():
    register_user({"name": "Test User", "email": TEST_EMAIL, "password": TEST_PASSWORD})
    token = client.post("/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD}).json()["access_token"]

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    body = response.json()
    assert body["email"] == TEST_EMAIL
    assert body["name"] == "Test User"
    assert "password" not in body
    assert "password_hash" not in body


def test_registry_health_still_passes():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
