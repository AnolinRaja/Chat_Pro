import pytest
from pymongo.errors import PyMongoError

from app.db import db
from app.services.email_service import EmailService
from app.services.rate_limiter import auth_rate_limiter
from app.services.otp_service import OtpService


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