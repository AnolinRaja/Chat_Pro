from __future__ import annotations

import smtplib
import logging
import re
from email.message import EmailMessage

from app.config import settings

logger = logging.getLogger(__name__)


class EmailDeliveryError(Exception):
    """Raised when an email cannot be delivered."""


class EmailService:
    @staticmethod
    def _masked_email(email: str) -> str:
        local, separator, domain = email.partition("@")
        if not separator or not local:
            return "[EMAIL_REDACTED]"
        return f"{local[:1]}***@{domain}"

    @staticmethod
    def _safe_smtp_message(error: smtplib.SMTPException) -> str:
        value = getattr(error, "smtp_error", b"")
        if isinstance(value, bytes):
            value = value.decode("utf-8", errors="replace")
        value = re.sub(r"(?i)(password|passwd|secret|token|otp)\s*[=:]\s*[^\s,;]+", r"\1=[REDACTED]", str(value))
        return value[:300]

    @staticmethod
    def send_otp(recipient: str, otp: str, expires_in_minutes: int) -> None:
        if not settings.SMTP_HOST or not settings.SMTP_FROM_EMAIL:
            raise EmailDeliveryError("Email delivery is not configured.")

        message = EmailMessage()
        message["Subject"] = "Your ChatPRO verification code"
        message["From"] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>"
        message["To"] = recipient
        message.set_content(
            "Hello,\n\n"
            "Your ChatPRO verification code is:\n\n"
            f"{otp}\n\n"
            f"This code expires in {expires_in_minutes} minutes.\n\n"
            "If you did not request this code, you can safely ignore this email.\n"
        )
        masked_recipient = EmailService._masked_email(recipient)
        logger.info(
            "SMTP OTP delivery started host=%s port=%s username_configured=%s password_configured=%s sender=%s recipient=%s",
            settings.SMTP_HOST,
            settings.SMTP_PORT,
            bool(settings.SMTP_USERNAME),
            bool(settings.SMTP_PASSWORD),
            EmailService._masked_email(settings.SMTP_FROM_EMAIL),
            masked_recipient,
        )

        try:
            stage = "connection"
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as server:
                logger.info("SMTP OTP delivery stage=connection status=succeeded")
                stage = "starttls"
                server.starttls()
                logger.info("SMTP OTP delivery stage=starttls status=succeeded")
                if settings.SMTP_USERNAME:
                    stage = "authentication"
                    server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
                    logger.info("SMTP OTP delivery stage=authentication status=succeeded")
                stage = "sendmail"
                logger.info("SMTP OTP delivery stage=message_construction status=succeeded recipient=%s", masked_recipient)
                server.send_message(message)
                logger.info("SMTP OTP delivery stage=sendmail status=succeeded recipient=%s", masked_recipient)
        except (OSError, smtplib.SMTPException) as error:
            logger.error(
                "SMTP OTP delivery failed stage=%s exception=%s code=%s message=%s recipient=%s",
                stage,
                type(error).__name__,
                getattr(error, "smtp_code", None),
                EmailService._safe_smtp_message(error) if isinstance(error, smtplib.SMTPException) else "network failure",
                masked_recipient,
            )
            raise EmailDeliveryError("Unable to deliver email.") from error
