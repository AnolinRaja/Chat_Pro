from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from bson import ObjectId
from fastapi import HTTPException, status
from pymongo.errors import PyMongoError

from app.config import settings
from app.db import db


class SessionService:
    @staticmethod
    def _hash_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def create_session(user_id: str) -> tuple[str, str]:
        raw_token = secrets.token_urlsafe(32)
        token_hash = SessionService._hash_token(raw_token)
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)

        collection = db.get_db()["auth_sessions"]
        doc = {
            "user_id": ObjectId(user_id),
            "token_hash": token_hash,
            "created_at": now,
            "last_used_at": now,
            "expires_at": expires_at,
            "revoked_at": None,
        }
        try:
            result = collection.insert_one(doc)
            session_id = str(result.inserted_id)
            return session_id, raw_token
        except PyMongoError as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Unable to create session at this time."
            ) from e

    @staticmethod
    def validate_session(session_id: str, refresh_token: str) -> str:
        if not session_id or not refresh_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired session."
            )

        try:
            oid = ObjectId(session_id)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired session."
            )

        collection = db.get_db()["auth_sessions"]
        try:
            session = collection.find_one({"_id": oid})
        except PyMongoError as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database error during session validation."
            ) from e

        if session is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired session."
            )

        # Check token match
        submitted_hash = SessionService._hash_token(refresh_token)
        if session.get("token_hash") != submitted_hash:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired session."
            )

        # Check expiry
        now = datetime.now(timezone.utc)
        expires_at = session.get("expires_at")
        if expires_at is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired session."
            )
        
        # Ensure UTC timezone comparison
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= now:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired session."
            )

        # Check revocation
        if session.get("revoked_at") is not None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired session."
            )

        # Update last_used_at
        try:
            collection.update_one(
                {"_id": oid},
                {"$set": {"last_used_at": now}}
            )
        except PyMongoError as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database error during session update."
            ) from e

        return str(session["user_id"])

    @staticmethod
    def rotate_refresh_token(session_id: str, refresh_token: str) -> tuple[str, str, str]:
        # First validate the existing session/token to identify user
        user_id = SessionService.validate_session(session_id, refresh_token)

        new_raw_token = secrets.token_urlsafe(32)
        new_token_hash = SessionService._hash_token(new_raw_token)
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)

        collection = db.get_db()["auth_sessions"]
        try:
            result = collection.update_one(
                {"_id": ObjectId(session_id)},
                {
                    "$set": {
                        "token_hash": new_token_hash,
                        "last_used_at": now,
                        "expires_at": expires_at,
                    }
                }
            )
            if result.modified_count != 1:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid or expired session."
                )
            return session_id, new_raw_token, user_id
        except PyMongoError as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database error during token rotation."
            ) from e

    @staticmethod
    def revoke_session(session_id: str) -> None:
        try:
            oid = ObjectId(session_id)
        except Exception:
            return

        collection = db.get_db()["auth_sessions"]
        now = datetime.now(timezone.utc)
        try:
            collection.update_one(
                {"_id": oid},
                {"$set": {"revoked_at": now}}
            )
        except PyMongoError:
            pass

    @staticmethod
    def revoke_all_user_sessions(user_id: str) -> None:
        try:
            uid = ObjectId(user_id)
        except Exception:
            return

        collection = db.get_db()["auth_sessions"]
        now = datetime.now(timezone.utc)
        try:
            collection.update_many(
                {"user_id": uid, "revoked_at": None},
                {"$set": {"revoked_at": now}}
            )
        except PyMongoError:
            pass
