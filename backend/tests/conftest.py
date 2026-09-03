import os

# Deterministically isolate pytest to dedicated test database BEFORE any app imports
os.environ["MONGODB_DB"] = "chatpro_test"

import pytest
from pymongo.errors import PyMongoError

from app.config import settings
settings.MONGODB_DB = "chatpro_test"

from app.db import db
from app.services.email_service import EmailService
from app.services.rate_limiter import auth_rate_limiter
from app.services.otp_service import OtpService


def pytest_configure(config):
    """
    Critical Safety Guard:
    Ensure pytest is strictly executing against the isolated test database (chatpro_test).
    If pytest detects that the database is 'chatpro' or any non-test database,
    it unconditionally aborts to prevent data loss.
    """
    target_db = settings.MONGODB_DB
    if target_db == "chatpro" or not target_db.endswith("_test"):
        raise RuntimeError(
            f"FATAL SAFETY GUARD TRIGGERED: pytest attempted to run against database '{target_db}'. "
            "Tests must strictly run against a dedicated test database (e.g. 'chatpro_test') "
            "to prevent accidental deletion of development or production data."
        )
    # Ensure client is refreshed and indexes exist on the test database
    db.close_client()
    db.ensure_indexes()


@pytest.fixture(autouse=True)
def reset_auth_rate_limiter():
    auth_rate_limiter.clear()
    yield
    auth_rate_limiter.clear()


@pytest.fixture(autouse=True)
def isolate_otp_tests(request, monkeypatch):
    try:
        database = db.get_db()
        otp_collection = database["otp_codes"]
        challenge_collection = database["auth_challenges"]
    except (KeyError, TypeError):
        yield
        return

    try:
        otp_collection.delete_many({})
        challenge_collection.delete_many({})
    except PyMongoError:
        pass
    if request.node.fspath.basename != "test_otp_service.py":
        monkeypatch.setattr(EmailService, "send_otp", lambda *args, **kwargs: None)
        monkeypatch.setattr(OtpService, "generate_otp", lambda: "123456")
    yield
    try:
        otp_collection.delete_many({})
        challenge_collection.delete_many({})
    except PyMongoError:
        pass