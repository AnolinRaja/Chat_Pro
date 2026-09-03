from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import pyotp
from bson import ObjectId
from fastapi import HTTPException, status
from pymongo import ReturnDocument
from pymongo.errors import PyMongoError

from app.config import settings
from app.db import db

logger = logging.getLogger(__name__)


class TwoFactorService:
    @staticmethod
    def generate_secret() -> str:
        """Generate a cryptographically secure random base32 TOTP secret."""
        return pyotp.random_base32()

    @staticmethod
    def generate_otpauth_uri(secret: str, email: str) -> str:
        """Generate standard otpauth URI for authenticator applications (Google Authenticator, Apple Passwords, Authy, etc.)."""
        return pyotp.totp.TOTP(secret).provisioning_uri(
            name=email,
            issuer_name="ChatPRO"
        )

    @staticmethod
    def hash_recovery_code(user_id: str, code: str) -> str:
        """Compute a SHA-256 hash of a normalized recovery code bound to user_id."""
        normalized_code = code.strip().lower().replace(" ", "").replace("-", "")
        return hashlib.sha256(f"{user_id}:{normalized_code}".encode("utf-8")).hexdigest()

    @staticmethod
    def generate_recovery_codes(user_id: str, count: int = 8) -> tuple[list[str], list[str]]:
        """
        Generate plain-text recovery codes formatted as 'xxxx-xxxx' and their salted SHA-256 hashes.
        Returns: (plain_codes, hashed_codes)
        """
        plain_codes: list[str] = []
        hashed_codes: list[str] = []

        for _ in range(count):
            # Generate 8 random hex characters (4 bytes)
            raw_hex = secrets.token_hex(4)
            formatted_code = f"{raw_hex[:4]}-{raw_hex[4:]}"
            plain_codes.append(formatted_code)
            hashed_codes.append(TwoFactorService.hash_recovery_code(user_id, formatted_code))

        return plain_codes, hashed_codes

    @staticmethod
    def verify_totp(secret: str, code: str) -> bool:
        """
        Validate a 6-digit TOTP code against a base32 secret using RFC 6238.
        valid_window=1 allows the current 30s step plus 1 step on either side (tolerance for minor clock drift).
        """
        if not secret or not code:
            return False
        clean_code = code.strip().replace(" ", "").replace("-", "")
        if not clean_code.isdigit() or len(clean_code) != 6:
            return False
        try:
            totp = pyotp.TOTP(secret)
            return bool(totp.verify(clean_code, valid_window=1))
        except Exception:
            return False

    @staticmethod
    def setup_2sv(user_id: str, email: str) -> dict[str, Any]:
        """Initiate 2SV setup: generates secret & recovery codes in unconfirmed pending state."""
        secret = TwoFactorService.generate_secret()
        otpauth_uri = TwoFactorService.generate_otpauth_uri(secret, email)
        plain_recovery_codes, recovery_hashes = TwoFactorService.generate_recovery_codes(user_id)

        now = datetime.now(timezone.utc)
        collection = db.get_db()["users"]

        try:
            result = collection.update_one(
                {"_id": ObjectId(user_id)},
                {
                    "$set": {
                        "two_factor_pending_secret": secret,
                        "two_factor_pending_recovery_hashes": recovery_hashes,
                        "two_factor_pending_created_at": now,
                        "updated_at": now,
                    }
                }
            )
            if result.matched_count == 0:
                raise HTTPException(status_code=404, detail="User not found.")
        except PyMongoError as e:
            logger.error("Failed to store 2SV setup state for user %s: %s", user_id, e)
            raise HTTPException(status_code=500, detail="Unable to initialize Two-Step Verification.")

        return {
            "secret": secret,
            "otpauth_uri": otpauth_uri,
            "recovery_codes": plain_recovery_codes,
        }

    @staticmethod
    def confirm_2sv(user_id: str, code: str) -> dict[str, Any]:
        """Confirm 2SV setup with a valid TOTP code and activate it for the account."""
        collection = db.get_db()["users"]
        user = collection.find_one({"_id": ObjectId(user_id)})

        if not user:
            raise HTTPException(status_code=404, detail="User not found.")

        pending_secret = user.get("two_factor_pending_secret")
        pending_created_at = user.get("two_factor_pending_created_at")

        if not pending_secret or not pending_created_at:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Two-Step Verification setup has not been initiated."
            )

        # Check pending expiration
        now = datetime.now(timezone.utc)
        if pending_created_at.tzinfo is None:
            pending_created_at = pending_created_at.replace(tzinfo=timezone.utc)

        if now - pending_created_at > timedelta(minutes=settings.TWO_FACTOR_SETUP_EXPIRE_MINUTES):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Two-Step Verification setup session has expired. Please initiate setup again."
            )

        # Verify TOTP code
        if not TwoFactorService.verify_totp(pending_secret, code):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid verification code. Please check your authenticator app and try again."
            )

        recovery_hashes = user.get("two_factor_pending_recovery_hashes", [])

        try:
            collection.update_one(
                {"_id": ObjectId(user_id)},
                {
                    "$set": {
                        "two_factor_enabled": True,
                        "two_factor_secret": pending_secret,
                        "two_factor_recovery_hashes": recovery_hashes,
                        "two_factor_enabled_at": now,
                        "updated_at": now,
                    },
                    "$unset": {
                        "two_factor_pending_secret": "",
                        "two_factor_pending_recovery_hashes": "",
                        "two_factor_pending_created_at": "",
                    }
                }
            )
        except PyMongoError as e:
            logger.error("Failed to activate 2SV for user %s: %s", user_id, e)
            raise HTTPException(status_code=500, detail="Unable to activate Two-Step Verification.")

        return {
            "message": "Two-Step Verification has been enabled successfully.",
            "two_factor_enabled": True,
        }

    @staticmethod
    def disable_2sv(user_id: str, password_verified: bool, code: str) -> dict[str, Any]:
        """
        Disable 2SV: Requires prior password verification and a valid TOTP code or single-use recovery code.
        """
        if not password_verified:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid password."
            )

        collection = db.get_db()["users"]
        user = collection.find_one({"_id": ObjectId(user_id)})

        if not user or not user.get("two_factor_enabled"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Two-Step Verification is not enabled for this account."
            )

        clean_code = code.strip()
        code_valid = False

        # Try TOTP verification
        active_secret = user.get("two_factor_secret")
        if active_secret and TwoFactorService.verify_totp(active_secret, clean_code):
            code_valid = True
        else:
            # Try atomic recovery code verification and consumption
            recovery_hash = TwoFactorService.hash_recovery_code(user_id, clean_code)
            consumed_user = collection.find_one_and_update(
                {
                    "_id": ObjectId(user_id),
                    "two_factor_enabled": True,
                    "two_factor_recovery_hashes": recovery_hash,
                },
                {"$pull": {"two_factor_recovery_hashes": recovery_hash}},
                return_document=ReturnDocument.AFTER
            )
            if consumed_user is not None:
                code_valid = True

        if not code_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid verification code or recovery code."
            )

        now = datetime.now(timezone.utc)
        try:
            collection.update_one(
                {"_id": ObjectId(user_id)},
                {
                    "$set": {
                        "two_factor_enabled": False,
                        "updated_at": now,
                    },
                    "$unset": {
                        "two_factor_secret": "",
                        "two_factor_recovery_hashes": "",
                        "two_factor_enabled_at": "",
                        "two_factor_pending_secret": "",
                        "two_factor_pending_recovery_hashes": "",
                        "two_factor_pending_created_at": "",
                    }
                }
            )
        except PyMongoError as e:
            logger.error("Failed to disable 2SV for user %s: %s", user_id, e)
            raise HTTPException(status_code=500, detail="Unable to disable Two-Step Verification.")

        return {
            "message": "Two-Step Verification has been disabled successfully.",
            "two_factor_enabled": False,
        }

    @staticmethod
    def verify_and_consume_2sv(user_id: str, code: str) -> bool:
        """
        Validate 2SV during login: accepts a 6-digit TOTP code OR atomically consumes a valid recovery code.
        Returns True if authenticated, False otherwise.
        """
        collection = db.get_db()["users"]
        try:
            oid = ObjectId(user_id)
        except Exception:
            return False

        user = collection.find_one({"_id": oid})
        if not user or not user.get("two_factor_enabled"):
            return False

        clean_code = code.strip()

        # 1. Check TOTP code
        active_secret = user.get("two_factor_secret")
        if active_secret and TwoFactorService.verify_totp(active_secret, clean_code):
            return True

        # 2. Check & atomically consume recovery code
        recovery_hash = TwoFactorService.hash_recovery_code(user_id, clean_code)
        consumed_user = collection.find_one_and_update(
            {
                "_id": oid,
                "two_factor_enabled": True,
                "two_factor_recovery_hashes": recovery_hash,
            },
            {"$pull": {"two_factor_recovery_hashes": recovery_hash}},
            return_document=ReturnDocument.AFTER
        )
        return consumed_user is not None
