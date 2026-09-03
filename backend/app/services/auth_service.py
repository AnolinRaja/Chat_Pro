from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from bcrypt import checkpw, gensalt, hashpw
from bson import ObjectId
from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError, PyMongoError

from app.db import db
from app.config import settings
from app.schemas.user import UserCreate
from app.services.jwt_service import JWTService
from app.services.otp_service import OtpDeliveryError, OtpPurpose, OtpRateLimitError, OtpService, OtpStorageError, OtpVerificationError
from app.services.session_service import SessionService
from app.services.two_factor_service import TwoFactorService


class AuthService:
    @staticmethod
    def normalize_email(email: str) -> str:
        return email.strip().lower()

    @staticmethod
    def hash_password(password: str) -> str:
        return hashpw(password.encode("utf-8"), gensalt()).decode("utf-8")

    @staticmethod
    def verify_password(password: str, password_hash: str) -> bool:
        return checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))

    @staticmethod
    def create_user(payload: UserCreate) -> dict[str, Any]:
        collection = db.get_db()["users"]

        now = datetime.now(timezone.utc)
        doc = {
            "name": payload.name.strip(),
            "email": AuthService.normalize_email(payload.email),
            "password_hash": AuthService.hash_password(payload.password),
            "created_at": now,
            "updated_at": now,
            "email_verified": False,
            "two_factor_enabled": False,
        }

        try:
            result = collection.insert_one(doc)
        except DuplicateKeyError:
            raise HTTPException(status_code=409, detail="Email already registered.")
        except PyMongoError:
            raise HTTPException(status_code=500, detail="Unable to register user at this time.")

        created_user = collection.find_one({"_id": result.inserted_id})
        if created_user is None:
            raise HTTPException(status_code=500, detail="Unable to register user at this time.")

        return {
            "id": str(created_user["_id"]),
            "name": created_user["name"],
            "email": created_user["email"],
            "created_at": created_user["created_at"],
            "email_verified": created_user.get("email_verified", False),
            "requires_otp": True,
            "verification_required": True,
            "message": "Verification code sent to your email.",
        }

    @staticmethod
    def register_user(payload: UserCreate) -> dict[str, Any]:
        normalized_email = AuthService.normalize_email(payload.email)
        collection = db.get_db()["users"]
        existing = collection.find_one({"email": normalized_email})
        if existing is not None:
            if existing.get("email_verified", True):
                raise HTTPException(status_code=409, detail="Email already registered.")
            try:
                OtpService.request_otp(normalized_email, OtpPurpose.REGISTRATION)
            except OtpRateLimitError:
                if OtpService.has_active_otp(normalized_email, OtpPurpose.REGISTRATION):
                    return AuthService._verification_required_response(existing, "A verification code was recently sent.")
                raise HTTPException(status_code=429, detail="Too many verification requests. Please try again later.")
            except OtpDeliveryError as error:
                AuthService._remove_failed_otp(error)
                raise HTTPException(status_code=503, detail="Unable to send verification code. Please try again.")
            except OtpStorageError:
                raise HTTPException(status_code=503, detail="Unable to send verification code. Please try again.")
            return AuthService._verification_required_response(existing, "Email verification required.")

        created = AuthService.create_user(payload)
        otp_id = None
        try:
            result = OtpService.request_otp(normalized_email, OtpPurpose.REGISTRATION)
            otp_id = result.get("id")
        except OtpRateLimitError:
            AuthService._rollback_new_registration(collection, created["id"], otp_id)
            raise HTTPException(status_code=429, detail="Too many verification requests. Please try again later.")
        except OtpDeliveryError as error:
            AuthService._rollback_new_registration(collection, created["id"], error.otp_id)
            raise HTTPException(status_code=503, detail="Unable to send verification code. Please try again.")
        except OtpStorageError:
            AuthService._rollback_new_registration(collection, created["id"], otp_id)
            raise HTTPException(status_code=503, detail="Unable to send verification code. Please try again.")
        return created

    @staticmethod
    def _verification_required_response(existing: dict[str, Any], message: str) -> dict[str, Any]:
        return {
            "id": str(existing["_id"]),
            "name": existing["name"],
            "email": existing["email"],
            "created_at": existing["created_at"],
            "email_verified": False,
            "requires_otp": True,
            "verification_required": True,
            "message": message,
        }

    @staticmethod
    def _rollback_new_registration(users_collection: Any, user_id: str, otp_id: str | ObjectId | None) -> None:
        try:
            users_collection.delete_one({"_id": ObjectId(user_id), "email_verified": False})
        except PyMongoError:
            pass
        if otp_id is not None:
            try:
                db.get_db()["otp_codes"].delete_one({"_id": ObjectId(str(otp_id))})
            except (PyMongoError, TypeError, ValueError):
                pass

    @staticmethod
    def _remove_failed_otp(error: OtpDeliveryError) -> None:
        if error.otp_id is None:
            return
        try:
            db.get_db()["otp_codes"].delete_one({"_id": ObjectId(str(error.otp_id))})
        except (PyMongoError, TypeError, ValueError):
            pass

    @staticmethod
    def get_user_by_email(email: str) -> dict[str, Any] | None:
        return db.get_db()["users"].find_one({"email": AuthService.normalize_email(email)})

    @staticmethod
    def verify_credentials(email: str, password: str) -> dict[str, Any]:
        normalized_email = AuthService.normalize_email(email)
        user = db.get_db()["users"].find_one({"email": normalized_email})

        if user is None or not AuthService.verify_password(password, user.get("password_hash", "")):
            raise HTTPException(status_code=401, detail="Invalid email or password.")

        if user.get("email_verified", True) is False:
            raise HTTPException(status_code=403, detail="Email verification is required.")
        return user

    @staticmethod
    def login_user(email: str, password: str) -> dict[str, Any]:
        normalized_email = AuthService.normalize_email(email)
        user = db.get_db()["users"].find_one({"email": normalized_email})
        if user is None or not AuthService.verify_password(password, user.get("password_hash", "")):
            raise HTTPException(status_code=401, detail="Invalid email or password.")

        # If email is unverified, trigger/require registration OTP
        if user.get("email_verified", True) is False:
            try:
                OtpService.request_otp(user["email"], OtpPurpose.REGISTRATION)
            except OtpRateLimitError:
                pass
            except (OtpDeliveryError, OtpStorageError):
                raise HTTPException(status_code=503, detail="Unable to send verification code. Please try again.")

            return {
                "requires_otp": True,
                "email": user["email"],
                "purpose": OtpPurpose.REGISTRATION.value,
                "message": "Email verification required. Verification code sent to your email.",
            }

        # If 2SV is enabled, issue short-lived intermediate challenge token
        if user.get("two_factor_enabled", False):
            two_factor_token = JWTService.create_auth_challenge(str(user["_id"]), "2sv_login")
            return {
                "requires_2sv": True,
                "two_factor_token": two_factor_token,
                "message": "Two-Step Verification required.",
            }

        # Normal login (2SV OFF): return user directly for session/token generation
        return {
            "requires_2sv": False,
            "user": user,
        }

    @staticmethod
    def verify_2sv_login(two_factor_token: str, code: str) -> dict[str, Any]:
        try:
            payload = JWTService.decode_auth_challenge(two_factor_token, "2sv_login")
        except Exception:
            raise HTTPException(status_code=401, detail="Invalid or expired verification session.")

        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid or expired verification session.")

        # Validate TOTP code or atomically consume recovery code
        is_valid = TwoFactorService.verify_and_consume_2sv(user_id, code)
        if not is_valid:
            raise HTTPException(status_code=401, detail="Invalid verification code or recovery code.")

        user = db.get_db()["users"].find_one({"_id": ObjectId(user_id)})
        if not user or user.get("email_verified", True) is False:
            raise HTTPException(status_code=401, detail="Unable to complete sign in.")

        return user

    @staticmethod
    def verify_registration(email: str, otp: str) -> dict[str, Any]:
        normalized_email = AuthService.normalize_email(email)
        try:
            OtpService.verify_otp(normalized_email, OtpPurpose.REGISTRATION, otp)
        except OtpVerificationError:
            raise HTTPException(status_code=401, detail="Invalid verification code.")
        except OtpStorageError:
            raise HTTPException(status_code=503, detail="Unable to verify code. Please try again.")

        result = db.get_db()["users"].update_one(
            {"email": normalized_email, "email_verified": False},
            {"$set": {"email_verified": True, "updated_at": datetime.now(timezone.utc)}},
        )
        if result.modified_count != 1:
            raise HTTPException(status_code=400, detail="Unable to verify this account.")
        return {"message": "Email verified successfully."}

    @staticmethod
    def resend_registration(email: str) -> None:
        user = AuthService.get_user_by_email(email)
        if user is None or user.get("email_verified", True):
            raise HTTPException(status_code=400, detail="Unable to resend verification code.")
        try:
            OtpService.request_otp(user["email"], OtpPurpose.REGISTRATION)
        except OtpRateLimitError:
            raise HTTPException(status_code=429, detail="Too many verification requests. Please try again later.")
        except OtpDeliveryError as error:
            AuthService._remove_failed_otp(error)
            raise HTTPException(status_code=503, detail="Unable to send verification code. Please try again.")
        except OtpStorageError:
            raise HTTPException(status_code=503, detail="Unable to send verification code. Please try again.")

    @staticmethod
    def verify_login(email: str, otp: str) -> dict[str, str]:
        normalized_email = AuthService.normalize_email(email)
        try:
            OtpService.verify_otp(normalized_email, OtpPurpose.LOGIN, otp)
        except OtpVerificationError:
            raise HTTPException(status_code=401, detail="Invalid verification code.")
        except OtpStorageError:
            raise HTTPException(status_code=503, detail="Unable to verify code. Please try again.")

        user = AuthService.get_user_by_email(normalized_email)
        if user is None or user.get("email_verified", True) is False:
            raise HTTPException(status_code=401, detail="Unable to complete sign in.")

        access_token = JWTService.create_access_token(str(user["_id"]))
        return {
            "access_token": access_token,
            "token_type": "bearer",
        }

    @staticmethod
    def resend_login(email: str) -> None:
        user = AuthService.get_user_by_email(email)
        if user is None or user.get("email_verified", True) is False:
            raise HTTPException(status_code=400, detail="Unable to resend verification code.")
        try:
            OtpService.request_otp(user["email"], OtpPurpose.LOGIN)
        except OtpRateLimitError:
            raise HTTPException(status_code=429, detail="Too many verification requests. Please try again later.")
        except (OtpDeliveryError, OtpStorageError):
            raise HTTPException(status_code=503, detail="Unable to send verification code. Please try again.")

    @staticmethod
    def request_password_reset(email: str) -> None:
        user = AuthService.get_user_by_email(email)
        if user is None:
            return
        try:
            OtpService.request_otp(user["email"], OtpPurpose.PASSWORD_RESET)
        except (OtpRateLimitError, OtpDeliveryError, OtpStorageError):
            return

    @staticmethod
    def verify_password_reset(email: str, otp: str) -> str:
        normalized_email = AuthService.normalize_email(email)
        try:
            OtpService.verify_otp(normalized_email, OtpPurpose.PASSWORD_RESET, otp)
        except OtpVerificationError:
            raise HTTPException(status_code=401, detail="Invalid verification code.")
        except OtpStorageError:
            raise HTTPException(status_code=503, detail="Unable to verify code. Please try again.")

        user = AuthService.get_user_by_email(normalized_email)
        if user is None:
            raise HTTPException(status_code=401, detail="Invalid verification code.")
        challenge = JWTService.create_auth_challenge(str(user["_id"]), OtpPurpose.PASSWORD_RESET.value)
        now = datetime.now(timezone.utc)
        db.get_db()["auth_challenges"].insert_one({
            "jti": JWTService.decode_auth_challenge(challenge, OtpPurpose.PASSWORD_RESET.value)["jti"],
            "user_id": user["_id"],
            "purpose": OtpPurpose.PASSWORD_RESET.value,
            "created_at": now,
            "expires_at": now + timedelta(minutes=settings.OTP_CHALLENGE_EXPIRE_MINUTES),
            "used": False,
        })
        return challenge

    @staticmethod
    def complete_password_reset(reset_token: str, new_password: str) -> None:
        try:
            payload = JWTService.decode_auth_challenge(reset_token, OtpPurpose.PASSWORD_RESET.value)
            challenge = db.get_db()["auth_challenges"].find_one_and_update(
                {"jti": payload["jti"], "user_id": ObjectId(payload["sub"]), "purpose": OtpPurpose.PASSWORD_RESET.value, "used": False, "expires_at": {"$gt": datetime.now(timezone.utc)}},
                {"$set": {"used": True}},
            )
        except Exception:
            raise HTTPException(status_code=401, detail="Invalid or expired reset authorization.")
        if challenge is None:
            raise HTTPException(status_code=401, detail="Invalid or expired reset authorization.")
        try:
            db.get_db()["users"].update_one(
                {"_id": ObjectId(payload["sub"])},
                {"$set": {"password_hash": AuthService.hash_password(new_password), "updated_at": datetime.now(timezone.utc)}},
            )
            # Revoke all existing user sessions upon password reset for security
            SessionService.revoke_all_user_sessions(str(payload["sub"]))
        except PyMongoError:
            raise HTTPException(status_code=503, detail="Unable to reset password. Please try again.")
