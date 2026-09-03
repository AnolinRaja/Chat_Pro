import pytest
from fastapi.testclient import TestClient

from app.db import db
from app.main import app
from app.config import settings
from app.services.email_service import EmailDeliveryError, EmailService
from app.services.auth_service import AuthService

client = TestClient(app)
PASSWORD = "StrongPassword123"
EMAIL = "phase63@example.com"


@pytest.fixture(autouse=True)
def cleanup_users():
    db.get_db()["users"].delete_many({"email": EMAIL})
    yield
    db.get_db()["users"].delete_many({"email": EMAIL})


def register():
    return client.post("/auth/register", json={"name": "Phase Six", "email": EMAIL, "password": PASSWORD})


def verify_registration():
    return client.post("/auth/register/verify", json={"email": EMAIL, "otp": "123456"})


def login():
    return client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})


def verify_login():
    return client.post("/auth/login/verify", json={"email": EMAIL, "otp": "123456"})


def test_registration_creates_unverified_user_and_requires_verification():
    response = register()

    assert response.status_code == 201
    assert response.json()["requires_otp"] is True
    assert response.json()["email_verified"] is False
    assert "password" not in response.json()
    assert "password_hash" not in response.json()
    assert db.get_db()["users"].find_one({"email": EMAIL})["email_verified"] is False

    assert login().status_code == 200


def test_registration_otp_verification_marks_account_verified():
    register()

    response = verify_registration()

    assert response.status_code == 200
    assert "message" in response.json()
    assert db.get_db()["users"].find_one({"email": EMAIL})["email_verified"] is True


def test_failed_new_registration_rolls_back_user_and_otp(monkeypatch):
    monkeypatch.setattr(EmailService, "send_otp", lambda *args, **kwargs: (_ for _ in ()).throw(EmailDeliveryError("delivery failed")))

    response = register()

    assert response.status_code == 503
    assert db.get_db()["users"].find_one({"email": EMAIL}) is None
    assert db.get_db()["otp_codes"].count_documents({"identifier": EMAIL}) == 0


def test_existing_unverified_registration_can_recover_without_duplicate_user(monkeypatch):
    first = register()
    user = db.get_db()["users"].find_one({"email": EMAIL})
    user_id = user["_id"]
    monkeypatch.setattr(settings, "OTP_RESEND_COOLDOWN_SECONDS", 0)

    second = register()

    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json()["message"] == "Email verification required."
    assert db.get_db()["users"].count_documents({"email": EMAIL}) == 1
    assert db.get_db()["users"].find_one({"email": EMAIL})["_id"] == user_id
    assert verify_registration().status_code == 200


def test_existing_active_registration_otp_is_recoverable_during_cooldown():
    register()

    retry = register()

    assert retry.status_code == 201
    assert retry.json()["message"] == "A verification code was recently sent."
    assert db.get_db()["users"].count_documents({"email": EMAIL}) == 1
    assert verify_registration().status_code == 200


def test_failed_existing_account_resend_does_not_consume_registration_retry(monkeypatch):
    register()
    monkeypatch.setattr(settings, "OTP_RESEND_COOLDOWN_SECONDS", 0)
    monkeypatch.setattr(EmailService, "send_otp", lambda *args, **kwargs: (_ for _ in ()).throw(EmailDeliveryError("delivery failed")))

    failed = client.post("/auth/register/resend", json={"email": EMAIL})

    assert failed.status_code == 503
    assert db.get_db()["users"].count_documents({"email": EMAIL}) == 1
    assert db.get_db()["otp_codes"].count_documents({"identifier": EMAIL, "used": False}) == 0


def test_unverified_login_returns_registration_challenge_and_no_jwt():
    register()

    response = login()

    assert response.status_code == 200
    assert response.json()["purpose"] == "registration"
    assert "access_token" not in response.json()
    assert verify_registration().status_code == 200


def test_registration_otp_cannot_be_reused_or_used_for_login():
    register()

    assert client.post("/auth/login/verify", json={"email": EMAIL, "otp": "123456"}).status_code == 401
    assert verify_registration().status_code == 200
    assert verify_registration().status_code == 401


def test_unverified_login_requires_otp_and_does_not_issue_jwt_early():
    register()

    response = login()

    assert response.status_code == 200
    assert response.json()["requires_otp"] is True
    assert "access_token" not in response.json()
    verified = verify_registration()
    assert verified.status_code == 200
    login_success = login()
    assert login_success.status_code == 200
    assert "access_token" in login_success.json()


def test_login_invalid_otp_does_not_issue_jwt():
    register()
    response = client.post("/auth/login/verify", json={"email": EMAIL, "otp": "000000"})

    assert response.status_code == 401
    assert "access_token" not in response.json()


def test_login_otp_cannot_be_used_for_password_reset():
    register()
    verify_registration()

    response = client.post("/auth/forgot-password/verify", json={"email": EMAIL, "otp": "123456"})

    assert response.status_code == 401


def test_forgot_password_nonexistent_email_has_generic_response():
    response = client.post("/auth/forgot-password/request", json={"email": "missing@example.com"})

    assert response.status_code == 200
    assert response.json() == {"message": "If an account exists for this email, a verification code has been sent."}


def test_password_reset_replaces_bcrypt_password_and_challenge_is_single_use():
    register()
    verify_registration()
    request_response = client.post("/auth/forgot-password/request", json={"email": EMAIL})
    assert request_response.status_code == 200

    verify_response = client.post("/auth/forgot-password/verify", json={"email": EMAIL, "otp": "123456"})
    assert verify_response.status_code == 200
    reset_token = verify_response.json()["reset_token"]
    assert "password_hash" not in verify_response.text

    reset_response = client.post(
        "/auth/forgot-password/reset",
        json={"reset_token": reset_token, "new_password": "NewStrongPassword123"},
    )
    assert reset_response.status_code == 200
    assert "password_hash" not in reset_response.text

    assert client.post(
        "/auth/forgot-password/reset",
        json={"reset_token": reset_token, "new_password": "AnotherPassword123"},
    ).status_code == 401
    assert login().status_code == 401

    new_login = client.post("/auth/login", json={"email": EMAIL, "password": "NewStrongPassword123"})
    assert new_login.status_code == 200
    assert "access_token" in new_login.json()


def test_legacy_user_without_email_verified_field_remains_compatible():
    from app.services.auth_service import AuthService

    user = {
        "name": "Legacy User",
        "email": EMAIL,
        "password_hash": AuthService.hash_password(PASSWORD),
    }
    db.get_db()["users"].insert_one(user)

    response = login()

    assert response.status_code == 200
    assert "access_token" in response.json()
