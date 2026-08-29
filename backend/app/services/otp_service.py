from __future__ import annotations

import secrets
import logging
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Any

from bcrypt import checkpw, gensalt, hashpw
from bson import ObjectId
from pymongo.errors import PyMongoError

from app.config import settings
from app.db import db
from app.services.email_service import EmailDeliveryError, EmailService

logger = logging.getLogger(__name__)


class OtpPurpose(StrEnum):
    REGISTRATION = "registration"
    LOGIN = "login"
    PASSWORD_RESET = "password_reset"


class OtpError(Exception):
    """Base class for expected OTP service failures."""


class OtpRateLimitError(OtpError):
    pass


class OtpVerificationError(OtpError):
    pass


class OtpStorageError(OtpError):
    pass


class OtpDeliveryError(OtpError):
    def __init__(self, message: str, otp_id: ObjectId | None = None):
        super().__init__(message)
        self.otp_id = otp_id


class OtpService:
    @staticmethod
    def generate_otp() -> str:
        return f"{secrets.randbelow(1_000_000):06d}"

    @staticmethod
    def _hash_otp(otp: str) -> str:
        return hashpw(otp.encode("utf-8"), gensalt()).decode("utf-8")

    @staticmethod
    def _normalize_identifier(identifier: str) -> str:
        return identifier.strip().lower()

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value

    @staticmethod
    def has_active_otp(identifier: str, purpose: OtpPurpose) -> bool:
        now = datetime.now(timezone.utc)
        try:
            record = db.get_db()["otp_codes"].find_one({
                "identifier": OtpService._normalize_identifier(identifier),
                "purpose": purpose.value,
                "used": False,
            })
            return bool(record and OtpService._as_utc(record["expires_at"]) > now)
        except PyMongoError as error:
            logger.error("OTP active-record lookup failed category=mongodb_unavailable")
            raise OtpStorageError("Unable to inspect OTP state.") from error

    @staticmethod
    def request_otp(identifier: str, purpose: OtpPurpose) -> dict[str, Any]:
        normalized_identifier = OtpService._normalize_identifier(identifier)
        if not normalized_identifier:
            raise OtpError("OTP identifier is required.")
        if not isinstance(purpose, OtpPurpose):
            raise OtpError("Invalid OTP purpose.")

        now = datetime.now(timezone.utc)
        base_filter = {"identifier": normalized_identifier, "purpose": purpose.value}
        try:
            collection = db.get_db()["otp_codes"]
            latest = collection.find_one(base_filter, sort=[("created_at", -1)])
            if latest and (now - OtpService._as_utc(latest["created_at"])).total_seconds() < settings.OTP_RESEND_COOLDOWN_SECONDS:
                logger.info("OTP request rejected category=cooldown_exceeded purpose=%s", purpose.value)
                raise OtpRateLimitError("Please wait before requesting another code.")

            window_start = now - timedelta(hours=1)
            if collection.count_documents({**base_filter, "created_at": {"$gte": window_start}}) >= settings.OTP_MAX_REQUESTS_PER_HOUR:
                logger.info("OTP request rejected category=hourly_rate_limit_exceeded purpose=%s", purpose.value)
                raise OtpRateLimitError("Too many OTP requests. Please try again later.")

            collection.update_many({**base_filter, "used": False}, {"$set": {"used": True}})
            otp = OtpService.generate_otp()
            expires_at = now + timedelta(minutes=settings.OTP_EXPIRY_MINUTES)
            result = collection.insert_one({
                "identifier": normalized_identifier,
                "otp_hash": OtpService._hash_otp(otp),
                "purpose": purpose.value,
                "created_at": now,
                "expires_at": expires_at,
                "attempts": 0,
                "used": False,
            })
        except (OtpRateLimitError, OtpError):
            raise
        except PyMongoError as error:
            logger.error("OTP request failed category=otp_persistence_failed purpose=%s", purpose.value)
            raise OtpStorageError("Unable to create OTP.") from error

        try:
            EmailService.send_otp(normalized_identifier, otp, settings.OTP_EXPIRY_MINUTES)
        except EmailDeliveryError as error:
            try:
                collection.update_one({"_id": result.inserted_id}, {"$set": {"used": True}})
            except PyMongoError:
                pass
            logger.error("OTP request failed category=smtp_delivery_failed purpose=%s", purpose.value)
            raise OtpDeliveryError("Unable to deliver OTP.", result.inserted_id) from error
        except Exception as error:
            try:
                collection.update_one({"_id": result.inserted_id}, {"$set": {"used": True}})
            except PyMongoError:
                pass
            logger.error("OTP request failed category=email_delivery_failed purpose=%s", purpose.value)
            raise OtpDeliveryError("Unable to deliver OTP.", result.inserted_id) from error

        return {"id": str(result.inserted_id), "purpose": purpose.value, "expires_at": expires_at}

    @staticmethod
    def verify_otp(identifier: str, purpose: OtpPurpose, submitted_otp: str) -> bool:
        normalized_identifier = OtpService._normalize_identifier(identifier)
        if not isinstance(purpose, OtpPurpose) or not submitted_otp.isdigit() or len(submitted_otp) != 6:
            raise OtpVerificationError("Invalid OTP.")

        now = datetime.now(timezone.utc)
        try:
            collection = db.get_db()["otp_codes"]
            record = collection.find_one(
                {"identifier": normalized_identifier, "purpose": purpose.value, "used": False},
                sort=[("created_at", -1)],
            )
            if record is None or OtpService._as_utc(record["expires_at"]) <= now or record["attempts"] >= settings.OTP_MAX_ATTEMPTS:
                raise OtpVerificationError("Invalid OTP.")

            if not checkpw(submitted_otp.encode("utf-8"), record["otp_hash"].encode("utf-8")):
                update = {"$inc": {"attempts": 1}}
                if record["attempts"] + 1 >= settings.OTP_MAX_ATTEMPTS:
                    update["$set"] = {"used": True}
                collection.update_one({"_id": record["_id"], "used": False}, update)
                raise OtpVerificationError("Invalid OTP.")

            updated = collection.update_one(
                {"_id": record["_id"], "used": False, "attempts": {"$lt": settings.OTP_MAX_ATTEMPTS}},
                {"$set": {"used": True}},
            )
            if updated.modified_count != 1:
                raise OtpVerificationError("Invalid OTP.")
            return True
        except OtpVerificationError:
            raise
        except PyMongoError as error:
            raise OtpStorageError("Unable to verify OTP.") from error
