from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import secrets

import jwt

from app.config import settings


class JWTService:
    @staticmethod
    def create_access_token(subject: str) -> str:
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
        payload = {
            "sub": subject,
            "iat": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
        }
        return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

    @staticmethod
    def create_admin_access_token(
        admin_id: str,
        role: str,
        organization_id: str | None = None,
    ) -> str:
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
        payload = {
            "sub": admin_id,
            "type": "admin",
            "role": role,
            "org_id": organization_id,
            "iat": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
        }
        return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

    @staticmethod
    def decode_access_token(token: str) -> dict[str, Any]:
        return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])

    @staticmethod
    def create_auth_challenge(subject: str, purpose: str) -> str:
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(minutes=settings.OTP_CHALLENGE_EXPIRE_MINUTES)
        payload = {
            "sub": subject,
            "purpose": purpose,
            "jti": secrets.token_urlsafe(24),
            "iat": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
        }
        return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

    @staticmethod
    def decode_auth_challenge(token: str, purpose: str) -> dict[str, Any]:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        if payload.get("purpose") != purpose or not payload.get("jti") or not payload.get("sub"):
            raise ValueError("Invalid authentication challenge.")
        return payload
