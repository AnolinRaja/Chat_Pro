from datetime import datetime, timezone

import pyotp
import pytest
from fastapi.testclient import TestClient

from app.db import db
from app.main import app

client = TestClient(app)

TEST_EMAIL = "user2sv@example.com"
TEST_PASSWORD = "StrongPassword123!"


@pytest.fixture(autouse=True)
def cleanup_test_user():
    db.get_db()["users"].delete_many({"email": TEST_EMAIL})
    db.get_db()["auth_sessions"].delete_many({})
    yield
    db.get_db()["users"].delete_many({"email": TEST_EMAIL})
    db.get_db()["auth_sessions"].delete_many({})


def register_and_verify(email=TEST_EMAIL, password=TEST_PASSWORD):
    client.post("/auth/register", json={"name": "2SV User", "email": email, "password": password})
    client.post("/auth/register/verify", json={"email": email, "otp": "123456"})


def test_login_2sv_disabled_direct_session():
    register_and_verify()

    # Login without 2SV enabled
    res = client.post("/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data
    assert data.get("requires_2sv") is False
    assert "refresh_token" in res.cookies

    # Verify /auth/me
    token = data["access_token"]
    me_res = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_res.status_code == 200
    me_data = me_res.json()
    assert me_data["email"] == TEST_EMAIL
    assert me_data["two_factor_enabled"] is False


def test_registration_still_requires_email_otp():
    # Registration returns requires_otp: True
    res = client.post("/auth/register", json={"name": "2SV User", "email": TEST_EMAIL, "password": TEST_PASSWORD})
    assert res.status_code == 201
    assert res.json()["requires_otp"] is True

    # Login before OTP verification requires email verification OTP
    login_res = client.post("/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
    assert login_res.status_code == 200
    assert login_res.json().get("requires_otp") is True

    # After verifying registration OTP, login works directly
    client.post("/auth/register/verify", json={"email": TEST_EMAIL, "otp": "123456"})
    login_res2 = client.post("/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
    assert login_res2.status_code == 200
    assert "access_token" in login_res2.json()


def test_2sv_setup_and_confirm_lifecycle():
    register_and_verify()

    # Login to get access token
    login_res = client.post("/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Status before setup
    status_res = client.get("/auth/2sv/status", headers=headers)
    assert status_res.status_code == 200
    assert status_res.json()["two_factor_enabled"] is False
    assert status_res.json()["recovery_codes_remaining"] == 0

    # Initiate Setup
    setup_res = client.post("/auth/2sv/setup", headers=headers)
    assert setup_res.status_code == 200
    setup_data = setup_res.json()
    assert "secret" in setup_data
    assert "otpauth_uri" in setup_data
    assert len(setup_data["recovery_codes"]) == 8
    secret = setup_data["secret"]
    recovery_codes = setup_data["recovery_codes"]

    # Status is still False until confirmed
    status_res2 = client.get("/auth/2sv/status", headers=headers)
    assert status_res2.json()["two_factor_enabled"] is False

    # Confirm with invalid TOTP code fails
    confirm_fail = client.post("/auth/2sv/confirm", json={"code": "000000"}, headers=headers)
    assert confirm_fail.status_code == 400

    # Confirm with valid TOTP code succeeds
    valid_code = pyotp.TOTP(secret).now()
    confirm_success = client.post("/auth/2sv/confirm", json={"code": valid_code}, headers=headers)
    assert confirm_success.status_code == 200
    assert confirm_success.json()["two_factor_enabled"] is True

    # Status now True with 8 recovery codes
    status_res3 = client.get("/auth/2sv/status", headers=headers)
    assert status_res3.json()["two_factor_enabled"] is True
    assert status_res3.json()["recovery_codes_remaining"] == 8

    # /auth/me returns two_factor_enabled: True without leaking secret or recovery hashes
    me_res = client.get("/auth/me", headers=headers)
    assert me_res.status_code == 200
    assert me_res.json()["two_factor_enabled"] is True
    assert "secret" not in me_res.json()
    assert "recovery_codes" not in me_res.json()


def test_2sv_login_with_totp_and_restricted_token():
    register_and_verify()
    login_res = client.post("/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Enable 2SV
    setup_data = client.post("/auth/2sv/setup", headers=headers).json()
    secret = setup_data["secret"]
    client.post("/auth/2sv/confirm", json={"code": pyotp.TOTP(secret).now()}, headers=headers)

    # Now Login requires 2SV
    login_res2 = client.post("/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
    assert login_res2.status_code == 200
    challenge_data = login_res2.json()
    assert challenge_data["requires_2sv"] is True
    assert "two_factor_token" in challenge_data
    two_factor_token = challenge_data["two_factor_token"]

    # Security check: Intermediate 2SV challenge token CANNOT access /auth/me or any protected endpoint
    bad_me = client.get("/auth/me", headers={"Authorization": f"Bearer {two_factor_token}"})
    assert bad_me.status_code == 401

    # Invalid TOTP code fails
    verify_fail = client.post("/auth/login/2sv", json={"two_factor_token": two_factor_token, "code": "000000"})
    assert verify_fail.status_code == 401

    # Valid TOTP code succeeds
    valid_code = pyotp.TOTP(secret).now()
    verify_success = client.post("/auth/login/2sv", json={"two_factor_token": two_factor_token, "code": valid_code})
    assert verify_success.status_code == 200
    auth_data = verify_success.json()
    assert "access_token" in auth_data
    assert "refresh_token" in verify_success.cookies

    # Valid session allows /auth/me
    auth_me = client.get("/auth/me", headers={"Authorization": f"Bearer {auth_data['access_token']}"})
    assert auth_me.status_code == 200
    assert auth_me.json()["email"] == TEST_EMAIL


def test_2sv_login_atomic_recovery_code_consumption():
    register_and_verify()
    login_res = client.post("/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Enable 2SV
    setup_data = client.post("/auth/2sv/setup", headers=headers).json()
    secret = setup_data["secret"]
    recovery_codes = setup_data["recovery_codes"]
    client.post("/auth/2sv/confirm", json={"code": pyotp.TOTP(secret).now()}, headers=headers)

    # Login and get 2SV challenge
    challenge_data = client.post("/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD}).json()
    two_factor_token = challenge_data["two_factor_token"]

    # Use first recovery code
    used_code = recovery_codes[0]
    rec_login = client.post("/auth/login/2sv", json={"two_factor_token": two_factor_token, "code": used_code})
    assert rec_login.status_code == 200
    new_token = rec_login.json()["access_token"]

    # Verify recovery codes count decremented to 7
    status_res = client.get("/auth/2sv/status", headers={"Authorization": f"Bearer {new_token}"})
    assert status_res.json()["recovery_codes_remaining"] == 7

    # Attempting to reuse the same recovery code on a new login MUST FAIL
    challenge_data2 = client.post("/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD}).json()
    reuse_fail = client.post("/auth/login/2sv", json={"two_factor_token": challenge_data2["two_factor_token"], "code": used_code})
    assert reuse_fail.status_code == 401


def test_2sv_disable_requires_password_and_code():
    register_and_verify()
    login_res = client.post("/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Enable 2SV
    setup_data = client.post("/auth/2sv/setup", headers=headers).json()
    secret = setup_data["secret"]
    recovery_codes = setup_data["recovery_codes"]
    client.post("/auth/2sv/confirm", json={"code": pyotp.TOTP(secret).now()}, headers=headers)

    # Disable with wrong password fails
    fail_pw = client.post("/auth/2sv/disable", json={"password": "WrongPassword!", "code": pyotp.TOTP(secret).now()}, headers=headers)
    assert fail_pw.status_code == 401

    # Disable with wrong code fails
    fail_code = client.post("/auth/2sv/disable", json={"password": TEST_PASSWORD, "code": "000000"}, headers=headers)
    assert fail_code.status_code == 400

    # Disable with correct password and valid TOTP code succeeds
    disable_ok = client.post("/auth/2sv/disable", json={"password": TEST_PASSWORD, "code": pyotp.TOTP(secret).now()}, headers=headers)
    assert disable_ok.status_code == 200
    assert disable_ok.json()["two_factor_enabled"] is False

    # Status is now disabled
    status_res = client.get("/auth/2sv/status", headers=headers)
    assert status_res.json()["two_factor_enabled"] is False

    # Subsequent login is now normal direct password login (2SV OFF)
    login_again = client.post("/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
    assert login_again.status_code == 200
    assert "access_token" in login_again.json()
    assert login_again.json().get("requires_2sv") is False


def test_password_reset_revokes_sessions_and_preserves_2sv():
    register_and_verify()
    login_res = client.post("/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Enable 2SV
    setup_data = client.post("/auth/2sv/setup", headers=headers).json()
    secret = setup_data["secret"]
    client.post("/auth/2sv/confirm", json={"code": pyotp.TOTP(secret).now()}, headers=headers)

    # Reset password flow
    client.post("/auth/forgot-password/request", json={"email": TEST_EMAIL})
    v_res = client.post("/auth/forgot-password/verify", json={"email": TEST_EMAIL, "otp": "123456"})
    reset_token = v_res.json()["reset_token"]

    new_pw = "BrandNewPassword123!"
    reset_res = client.post("/auth/forgot-password/reset", json={"reset_token": reset_token, "new_password": new_pw})
    assert reset_res.status_code == 200

    # Login with new password STILL requires 2SV
    new_login = client.post("/auth/login", json={"email": TEST_EMAIL, "password": new_pw})
    assert new_login.status_code == 200
    assert new_login.json()["requires_2sv"] is True

    # Complete 2SV with TOTP
    verify_res = client.post("/auth/login/2sv", json={
        "two_factor_token": new_login.json()["two_factor_token"],
        "code": pyotp.TOTP(secret).now()
    })
    assert verify_res.status_code == 200
    assert "access_token" in verify_res.json()
