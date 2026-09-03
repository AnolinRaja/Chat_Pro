from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.db import db
from app.main import app

client = TestClient(app)

TEST_EMAILS = {
    "rate-one@example.com",
    "rate-two@example.com",
    "rate-limit@example.com",
    "rate-limit-two@example.com",
    "window-one@example.com",
    "window-two@example.com",
    "window-three@example.com",
    "isolated@example.com",
    "successful-login@example.com",
}


@pytest.fixture(autouse=True)
def cleanup_security_test_users():
    users = db.get_db()["users"]
    users.delete_many({"email": {"$in": list(TEST_EMAILS)}})
    yield
    users.delete_many({"email": {"$in": list(TEST_EMAILS)}})


def test_auth_requests_below_limit_succeed():
    with patch("app.routes.auth.settings.AUTH_RATE_LIMIT_REQUESTS", 2):
        first = client.post(
            "/auth/register",
            json={"name": "Rate User One", "email": "rate-one@example.com", "password": "Password123"},
        )
        second = client.post(
            "/auth/register",
            json={"name": "Rate User Two", "email": "rate-two@example.com", "password": "Password123"},
        )

    assert first.status_code == 201
    assert second.status_code == 201


def test_auth_request_over_limit_returns_429_and_retry_after():
    with patch("app.routes.auth.settings.AUTH_RATE_LIMIT_REQUESTS", 1):
        first = client.post(
            "/auth/register",
            json={"name": "Rate User", "email": "rate-limit@example.com", "password": "Password123"},
        )
        second = client.post(
            "/auth/register",
            json={"name": "Rate User Two", "email": "rate-limit-two@example.com", "password": "Password123"},
        )

    assert first.status_code == 201
    assert second.status_code == 429
    assert second.headers["retry-after"].isdigit()
    assert second.json()["detail"] == "Too many authentication requests. Try again later."


def test_rate_limit_window_expiry_allows_request_again(monkeypatch):
    current_time = 100.0
    monkeypatch.setattr("app.services.rate_limiter.time.monotonic", lambda: current_time)

    with patch("app.routes.auth.settings.AUTH_RATE_LIMIT_REQUESTS", 1), patch(
        "app.routes.auth.settings.AUTH_RATE_LIMIT_WINDOW_SECONDS", 10
    ):
        first = client.post(
            "/auth/register",
            json={"name": "Window User", "email": "window-one@example.com", "password": "Password123"},
        )
        blocked = client.post(
            "/auth/register",
            json={"name": "Window User Two", "email": "window-two@example.com", "password": "Password123"},
        )
        current_time = 110.0
        allowed = client.post(
            "/auth/register",
            json={"name": "Window User Three", "email": "window-three@example.com", "password": "Password123"},
        )

    assert first.status_code == 201
    assert blocked.status_code == 429
    assert allowed.status_code == 201


def test_login_and_registration_have_isolated_rate_limit_buckets():
    with patch("app.routes.auth.settings.AUTH_RATE_LIMIT_REQUESTS", 1):
        registration = client.post(
            "/auth/register",
            json={"name": "Isolated User", "email": "isolated@example.com", "password": "Password123"},
        )
        login = client.post(
            "/auth/login",
            json={"email": "isolated@example.com", "password": "Password123"},
        )

    assert registration.status_code == 201
    assert login.status_code == 200
    assert login.json()["purpose"] == "registration"
    assert "access_token" not in login.json()


def test_successful_login_with_2sv_off_issues_token_directly():
    client.post(
        "/auth/register",
        json={"name": "Successful Login", "email": "successful-login@example.com", "password": "Password123"},
    )
    client.post("/auth/register/verify", json={"email": "successful-login@example.com", "otp": "123456"})

    response = client.post(
        "/auth/login",
        json={"email": "successful-login@example.com", "password": "Password123"},
    )

    assert response.status_code == 200
    assert response.json()["requires_2sv"] is False
    assert "access_token" in response.json()