from __future__ import annotations

import logging
import re
import smtplib
import ssl
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
    def _safe_error_message(error: Exception) -> str:
        if isinstance(error, smtplib.SMTPException):
            value = getattr(error, "smtp_error", b"")
            if isinstance(value, bytes):
                value = value.decode("utf-8", errors="replace")
            msg = str(value) if value else str(error)
        else:
            msg = f"{type(error).__name__}: {error}"
        sanitized = re.sub(r"(?i)(password|passwd|secret|token|otp|auth)\s*[=:]\s*[^\s,;]+", r"\1=[REDACTED]", msg)
        return sanitized[:300]

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
        use_ssl = settings.SMTP_USE_SSL or (settings.SMTP_PORT == 465)

        logger.info(
            "SMTP OTP delivery started host=%s port=%s use_ssl=%s username_configured=%s password_configured=%s sender=%s recipient=%s",
            settings.SMTP_HOST,
            settings.SMTP_PORT,
            use_ssl,
            bool(settings.SMTP_USERNAME),
            bool(settings.SMTP_PASSWORD),
            EmailService._masked_email(settings.SMTP_FROM_EMAIL),
            masked_recipient,
        )

        ssl_context = ssl.create_default_context()
        try:
            stage = "connection"
            if use_ssl:
                server_cm = smtplib.SMTP_SSL(
                    settings.SMTP_HOST,
                    settings.SMTP_PORT,
                    timeout=settings.SMTP_TIMEOUT_SECONDS,
                    context=ssl_context,
                )
            else:
                server_cm = smtplib.SMTP(
                    settings.SMTP_HOST,
                    settings.SMTP_PORT,
                    timeout=settings.SMTP_TIMEOUT_SECONDS,
                )

            with server_cm as server:
                logger.info("SMTP OTP delivery stage=connection status=succeeded use_ssl=%s", use_ssl)
                if not use_ssl and settings.SMTP_USE_TLS:
                    stage = "starttls"
                    server.starttls(context=ssl_context)
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
            safe_msg = EmailService._safe_error_message(error)
            logger.error(
                "SMTP OTP delivery failed stage=%s exception=%s code=%s message=%s recipient=%s",
                stage,
                type(error).__name__,
                getattr(error, "smtp_code", None),
                safe_msg,
                masked_recipient,
            )
            raise EmailDeliveryError("Unable to deliver email.") from error
