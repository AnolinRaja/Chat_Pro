import pytest
from fastapi.testclient import TestClient

from app.db import db
from app.main import app

client = TestClient(app)

TEST_EMAILS = [
    "anolin@example.com",
    "phase2@example.com",
    "duplicate@example.com",
    "dup@example.com",
]


@pytest.fixture(autouse=True)
def cleanup_users():
    collection = db.get_db()["users"]
    collection.delete_many({"email": {"$in": TEST_EMAILS}})
    yield
    collection.delete_many({"email": {"$in": TEST_EMAILS}})


def register_user(payload):
    return client.post("/auth/register", json=payload)


def test_register_user_success():
    payload = {
        "name": "Anolin Raja",
        "email": "anolin@example.com",
        "password": "StrongPassword123",
    }

    response = register_user(payload)

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Anolin Raja"
    assert data["email"] == "anolin@example.com"
    assert "password" not in data
    assert "password_hash" not in data
    assert "id" in data
    assert "created_at" in data

    saved_user = db.get_db()["users"].find_one({"email": "anolin@example.com"})
    assert saved_user is not None
    assert saved_user["password_hash"] != "StrongPassword123"
    assert "password" not in saved_user


def test_register_missing_name():
    response = register_user({"email": "phase2@example.com", "password": "StrongPassword123"})
    assert response.status_code == 422


def test_register_missing_email():
    response = register_user({"name": "Anolin Raja", "password": "StrongPassword123"})
    assert response.status_code == 422


def test_register_invalid_email_format():
    response = register_user({
        "name": "Anolin Raja",
        "email": "not-an-email",
        "password": "StrongPassword123",
    })
    assert response.status_code == 422


def test_register_missing_password():
    response = register_user({"name": "Anolin Raja", "email": "phase2@example.com"})
    assert response.status_code == 422


def test_register_short_password():
    response = register_user({
        "name": "Anolin Raja",
        "email": "phase2@example.com",
        "password": "short",
    })
    assert response.status_code == 422


def test_register_whitespace_only_name_rejected():
    response = register_user({
        "name": "   ",
        "email": "phase2@example.com",
        "password": "StrongPassword123",
    })

    assert response.status_code == 422


def test_register_duplicate_email_rejected():
    first = register_user({
        "name": "First User",
        "email": "duplicate@example.com",
        "password": "StrongPassword123",
    })
    assert first.status_code == 201

    second = register_user({
        "name": "Second User",
        "email": "DUPLICATE@EXAMPLE.COM",
        "password": "AnotherStrongPass123",
    })

    assert second.status_code == 409
    assert second.json()["detail"] == "Email already registered."


def test_register_normalizes_email_to_lowercase():
    response = register_user({
        "name": "Normal User",
        "email": "  PHASE2@EXAMPLE.COM  ",
        "password": "StrongPassword123",
    })

    assert response.status_code == 201
    assert response.json()["email"] == "phase2@example.com"

    saved_user = db.get_db()["users"].find_one({"email": "phase2@example.com"})
    assert saved_user is not None
    assert saved_user["email"] == "phase2@example.com"


def test_registration_response_does_not_expose_sensitive_fields():
    response = register_user({
        "name": "Sensitive User",
        "email": "dup@example.com",
        "password": "StrongPassword123",
    })

    assert response.status_code == 201
    payload = response.json()
    assert "password" not in payload
    assert "password_hash" not in payload


def test_health_endpoint_still_passes():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
