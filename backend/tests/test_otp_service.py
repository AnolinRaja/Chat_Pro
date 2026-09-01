from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from pymongo.errors import PyMongoError

from app.config import settings
from app.db import db
from app.services.email_service import EmailDeliveryError, EmailService
from app.services.otp_service import (
    OtpDeliveryError,
    OtpPurpose,
    OtpRateLimitError,
    OtpService,
    OtpStorageError,
    OtpVerificationError,
)


IDENTIFIER = "otp-tests@example.com"


@pytest.fixture(autouse=True)
def cleanup_otp_data():
    collection = db.get_db()["otp_codes"]
    collection.delete_many({"identifier": IDENTIFIER})
    yield
    try:
        collection.delete_many({"identifier": IDENTIFIER})
    except PyMongoError:
        pass


def issue_otp(purpose=OtpPurpose.LOGIN, value="123456"):
    with patch.object(OtpService, "generate_otp", return_value=value), patch.object(EmailService, "send_otp"):
        return OtpService.request_otp(IDENTIFIER, purpose)


def test_generation_is_six_numeric_digits_and_uses_secure_source():
    with patch("app.services.otp_service.secrets.randbelow", return_value=42) as secure_random:
        otp = OtpService.generate_otp()

    assert otp == "000042"
    assert len(otp) == 6 and otp.isdigit()
    secure_random.assert_called_once_with(1_000_000)


def test_otp_is_stored_hashed_and_not_returned():
    result = issue_otp()
    stored = db.get_db()["otp_codes"].find_one({"identifier": IDENTIFIER})

    assert "otp" not in result
    assert "otp_hash" not in result
    assert stored["otp_hash"] != "123456"
    assert stored["otp_hash"].startswith("$2")
    assert "otp" not in stored


def test_correct_otp_verifies_successfully_and_cannot_be_reused():
    issue_otp()

    assert OtpService.verify_otp(IDENTIFIER, OtpPurpose.LOGIN, "123456") is True
    with pytest.raises(OtpVerificationError):
        OtpService.verify_otp(IDENTIFIER, OtpPurpose.LOGIN, "123456")


def test_incorrect_otp_fails():
    issue_otp()

    with pytest.raises(OtpVerificationError):
        OtpService.verify_otp(IDENTIFIER, OtpPurpose.LOGIN, "654321")


def test_fifth_failed_attempt_invalidates_otp_and_sixth_is_rejected():
    issue_otp()

    for _ in range(settings.OTP_MAX_ATTEMPTS):
        with pytest.raises(OtpVerificationError):
            OtpService.verify_otp(IDENTIFIER, OtpPurpose.LOGIN, "000000")

    stored = db.get_db()["otp_codes"].find_one({"identifier": IDENTIFIER})
    assert stored["attempts"] == settings.OTP_MAX_ATTEMPTS
    assert stored["used"] is True
    with pytest.raises(OtpVerificationError):
        OtpService.verify_otp(IDENTIFIER, OtpPurpose.LOGIN, "000000")


def test_expired_otp_fails():
    issue_otp()
    db.get_db()["otp_codes"].update_one(
        {"identifier": IDENTIFIER},
        {"$set": {"expires_at": datetime.now(timezone.utc) - timedelta(seconds=1)}},
    )

    with pytest.raises(OtpVerificationError):
        OtpService.verify_otp(IDENTIFIER, OtpPurpose.LOGIN, "123456")


def test_new_otp_invalidates_previous_otp():
    issue_otp(value="123456")
    db.get_db()["otp_codes"].update_many(
        {"identifier": IDENTIFIER},
        {"$set": {"created_at": datetime.now(timezone.utc) - timedelta(seconds=settings.OTP_RESEND_COOLDOWN_SECONDS + 1)}},
    )
    issue_otp(value="654321")

    with pytest.raises(OtpVerificationError):
        OtpService.verify_otp(IDENTIFIER, OtpPurpose.LOGIN, "123456")
    assert OtpService.verify_otp(IDENTIFIER, OtpPurpose.LOGIN, "654321") is True


def test_resend_cooldown_applies_per_purpose():
    issue_otp(OtpPurpose.LOGIN)

    with pytest.raises(OtpRateLimitError):
        issue_otp(OtpPurpose.LOGIN, value="654321")
    with patch.object(EmailService, "send_otp"):
        result = OtpService.request_otp(IDENTIFIER, OtpPurpose.REGISTRATION)
    assert result["purpose"] == OtpPurpose.REGISTRATION.value


def test_hourly_generation_limit_applies_per_identifier_and_purpose(monkeypatch):
    monkeypatch.setattr(settings, "OTP_MAX_REQUESTS_PER_HOUR", 2)
    for index in range(2):
        db.get_db()["otp_codes"].insert_one({
            "identifier": IDENTIFIER,
            "purpose": OtpPurpose.LOGIN.value,
            "otp_hash": "not-a-real-hash",
            "created_at": datetime.now(timezone.utc) - timedelta(seconds=(index + 1) * 61),
            "expires_at": datetime.now(timezone.utc) + timedelta(minutes=5),
            "attempts": 0,
            "used": True,
        })

    with pytest.raises(OtpRateLimitError):
        issue_otp()


def test_purposes_have_independent_verification_flows():
    issue_otp(OtpPurpose.LOGIN)

    with pytest.raises(OtpVerificationError):
        OtpService.verify_otp(IDENTIFIER, OtpPurpose.REGISTRATION, "123456")
    assert OtpService.verify_otp(IDENTIFIER, OtpPurpose.LOGIN, "123456") is True


def test_invalid_otp_format_fails_without_database_lookup():
    with pytest.raises(OtpVerificationError):
        OtpService.verify_otp(IDENTIFIER, OtpPurpose.LOGIN, "12ab56")


def test_otp_is_not_logged(caplog):
    with patch.object(EmailService, "send_otp"):
        OtpService.request_otp(IDENTIFIER, OtpPurpose.LOGIN)

    assert "123456" not in caplog.text


def test_mongodb_failure_is_handled_safely(monkeypatch):
    monkeypatch.setattr(db, "get_db", lambda: (_ for _ in ()).throw(PyMongoError("database unavailable")))

    with patch.object(OtpService, "generate_otp", return_value="123456"), pytest.raises(OtpStorageError):
        OtpService.request_otp(IDENTIFIER, OtpPurpose.LOGIN)
    with pytest.raises(OtpStorageError):
        OtpService.verify_otp(IDENTIFIER, OtpPurpose.LOGIN, "123456")


def test_email_delivery_failure_does_not_leave_active_otp(monkeypatch):
    monkeypatch.setattr(EmailService, "send_otp", lambda *args: (_ for _ in ()).throw(EmailDeliveryError("delivery failed")))

    with patch.object(OtpService, "generate_otp", return_value="123456"), pytest.raises(OtpDeliveryError):
        OtpService.request_otp(IDENTIFIER, OtpPurpose.LOGIN)

    stored = db.get_db()["otp_codes"].find_one({"identifier": IDENTIFIER})
    assert stored["used"] is True


def test_email_service_requires_configuration(monkeypatch):
    monkeypatch.setattr(settings, "SMTP_HOST", "")
    monkeypatch.setattr(settings, "SMTP_FROM_EMAIL", "")

    with pytest.raises(EmailDeliveryError):
        EmailService.send_otp(IDENTIFIER, "123456", settings.OTP_EXPIRY_MINUTES)


def test_email_service_preserves_safe_smtp_data_error_diagnostic(caplog):
    smtp_error = __import__("smtplib").SMTPDataError(550, b"5.4.5 Daily user sending limit exceeded")
    smtp_server = __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock()
    smtp_server.__enter__.return_value.send_message.side_effect = smtp_error

    with patch("app.services.email_service.smtplib.SMTP", return_value=smtp_server), caplog.at_level("ERROR"):
        with pytest.raises(EmailDeliveryError) as error:
            EmailService.send_otp(IDENTIFIER, "123456", settings.OTP_EXPIRY_MINUTES)

    assert isinstance(error.value.__cause__, __import__("smtplib").SMTPDataError)
    assert "SMTP OTP delivery failed stage=sendmail" in caplog.text
    assert "SMTPDataError" in caplog.text
    assert "550" in caplog.text
    assert "123456" not in caplog.text


def test_email_service_uses_smtp_ssl_for_port_465(monkeypatch):
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.example.com")
    monkeypatch.setattr(settings, "SMTP_PORT", 465)
    monkeypatch.setattr(settings, "SMTP_FROM_EMAIL", "sender@example.com")
    monkeypatch.setattr(settings, "SMTP_USERNAME", "user")
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "secret")

    mock_server = __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock()
    mock_server.__enter__.return_value = mock_server

    with patch("app.services.email_service.smtplib.SMTP_SSL", return_value=mock_server) as mock_ssl_class:
        EmailService.send_otp(IDENTIFIER, "654321", 5)

    mock_ssl_class.assert_called_once()
    mock_server.login.assert_called_once_with("user", "secret")
    mock_server.send_message.assert_called_once()


def test_email_service_uses_starttls_for_port_587(monkeypatch):
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.example.com")
    monkeypatch.setattr(settings, "SMTP_PORT", 587)
    monkeypatch.setattr(settings, "SMTP_FROM_EMAIL", "sender@example.com")
    monkeypatch.setattr(settings, "SMTP_USERNAME", "user")
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "secret")

    mock_server = __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock()
    mock_server.__enter__.return_value = mock_server

    with patch("app.services.email_service.smtplib.SMTP", return_value=mock_server) as mock_smtp_class:
        EmailService.send_otp(IDENTIFIER, "654321", 5)

    mock_smtp_class.assert_called_once()
    mock_server.starttls.assert_called_once()
    mock_server.login.assert_called_once_with("user", "secret")
    mock_server.send_message.assert_called_once()


def test_email_service_handles_oserror_network_failure(monkeypatch, caplog):
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.example.com")
    monkeypatch.setattr(settings, "SMTP_PORT", 587)
    monkeypatch.setattr(settings, "SMTP_FROM_EMAIL", "sender@example.com")

    with patch("app.services.email_service.smtplib.SMTP", side_effect=OSError("Network is unreachable")), caplog.at_level("ERROR"):
        with pytest.raises(EmailDeliveryError):
            EmailService.send_otp(IDENTIFIER, "123456", 5)

    assert "SMTP OTP delivery failed stage=connection" in caplog.text
    assert "OSError" in caplog.text
    assert "Network is unreachable" in caplog.text
    assert "123456" not in caplog.text


def test_email_service_uses_resend_api_when_configured(monkeypatch):
    monkeypatch.setattr(settings, "EMAIL_PROVIDER", "resend")
    monkeypatch.setattr(settings, "RESEND_API_KEY", "re_test_key_123")
    monkeypatch.setattr(settings, "SMTP_FROM_EMAIL", "sender@example.com")
    monkeypatch.setattr(settings, "SMTP_FROM_NAME", "ChatPRO")

    mock_response = __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock()
    mock_response.is_error = False
    mock_response.status_code = 200

    with patch("httpx.Client.post", return_value=mock_response) as mock_post:
        EmailService.send_otp(IDENTIFIER, "123456", 5)

    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args
    assert args[0] == "https://api.resend.com/emails"
    assert "Bearer re_test_key_123" in kwargs["headers"]["Authorization"]
    assert kwargs["json"]["to"] == [IDENTIFIER]
    assert "123456" in kwargs["json"]["text"]


def test_email_service_handles_resend_api_error(monkeypatch, caplog):
    monkeypatch.setattr(settings, "EMAIL_PROVIDER", "resend")
    monkeypatch.setattr(settings, "RESEND_API_KEY", "re_test_key_123")
    monkeypatch.setattr(settings, "SMTP_FROM_EMAIL", "sender@example.com")

    mock_response = __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock()
    mock_response.is_error = True
    mock_response.status_code = 403
    mock_response.text = "Forbidden domain"

    with patch("httpx.Client.post", return_value=mock_response), caplog.at_level("ERROR"):
        with pytest.raises(EmailDeliveryError):
            EmailService.send_otp(IDENTIFIER, "123456", 5)

    assert "Resend API error status_code=403" in caplog.text
    assert "123456" not in caplog.text


def test_email_service_uses_sendgrid_api_when_configured(monkeypatch):
    monkeypatch.setattr(settings, "EMAIL_PROVIDER", "sendgrid")
    monkeypatch.setattr(settings, "SENDGRID_API_KEY", "SG.test_key_123")
    monkeypatch.setattr(settings, "SMTP_FROM_EMAIL", "sender@example.com")
    monkeypatch.setattr(settings, "SMTP_FROM_NAME", "ChatPRO")

    mock_response = __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock()
    mock_response.status_code = 202

    with patch("httpx.Client.post", return_value=mock_response) as mock_post:
        EmailService.send_otp(IDENTIFIER, "123456", 5)

    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args
    assert args[0] == "https://api.sendgrid.com/v3/mail/send"
    assert "Bearer SG.test_key_123" in kwargs["headers"]["Authorization"]
    assert kwargs["json"]["personalizations"][0]["to"][0]["email"] == IDENTIFIER
    assert "123456" in kwargs["json"]["content"][0]["value"]


def test_email_service_handles_sendgrid_api_error(monkeypatch, caplog):
    monkeypatch.setattr(settings, "EMAIL_PROVIDER", "sendgrid")
    monkeypatch.setattr(settings, "SENDGRID_API_KEY", "SG.test_key_123")
    monkeypatch.setattr(settings, "SMTP_FROM_EMAIL", "sender@example.com")

    mock_response = __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock()
    mock_response.status_code = 401
    mock_response.text = "Unauthorized"

    with patch("httpx.Client.post", return_value=mock_response), caplog.at_level("ERROR"):
        with pytest.raises(EmailDeliveryError):
            EmailService.send_otp(IDENTIFIER, "123456", 5)

    assert "SendGrid API error status_code=401" in caplog.text
    assert "123456" not in caplog.text
