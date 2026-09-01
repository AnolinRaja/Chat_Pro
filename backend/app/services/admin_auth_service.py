from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
import bcrypt
from bson import ObjectId
from fastapi import HTTPException, status
from pymongo.errors import DuplicateKeyError, PyMongoError

from app.db import db
from app.schemas.admin import AdminCreate

logger = logging.getLogger(__name__)


class AdminAuthService:
    @staticmethod
    def normalize_email(email: str) -> str:
        return email.strip().lower()

    @staticmethod
    def hash_password(password: str) -> str:
        return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    @staticmethod
    def verify_password(password: str, password_hash: str) -> bool:
        try:
            return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
        except Exception:
            return False

    @staticmethod
    def create_admin(payload: AdminCreate) -> dict[str, Any]:
        normalized_email = AdminAuthService.normalize_email(payload.email)

        if payload.role not in {"system_admin", "org_admin"}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid admin role."
            )

        org_oid: ObjectId | None = None
        if payload.role == "system_admin":
            if payload.organization_id is not None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="System administrator must not be associated with an organization."
                )
        elif payload.role == "org_admin":
            if not payload.organization_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Organization administrator must be associated with an organization."
                )
            try:
                org_oid = ObjectId(payload.organization_id)
            except Exception:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid organization ID format."
                )
            org = db.get_db()["organizations"].find_one({"_id": org_oid})
            if not org:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Organization not found."
                )

        now = datetime.now(timezone.utc)
        password_hash = AdminAuthService.hash_password(payload.password)

        doc = {
            "email": normalized_email,
            "name": payload.name.strip(),
            "password_hash": password_hash,
            "role": payload.role,
            "organization_id": org_oid,
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        }

        collection = db.get_db()["admin_users"]
        try:
            result = collection.insert_one(doc)
        except DuplicateKeyError:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Admin email already registered."
            )
        except PyMongoError as e:
            logger.error("Failed to create admin account: %s", e)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Unable to create admin account at this time."
            )

        created = collection.find_one({"_id": result.inserted_id})
        if not created:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Unable to verify admin creation."
            )

        return AdminAuthService._format_admin(created)

    @staticmethod
    def authenticate_admin(email: str, password: str) -> dict[str, Any]:
        normalized_email = AdminAuthService.normalize_email(email)
        collection = db.get_db()["admin_users"]

        try:
            admin = collection.find_one({"email": normalized_email})
        except PyMongoError as e:
            logger.error("Database error during admin authentication: %s", e)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database error during authentication."
            )

        if not admin:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password."
            )

        if not admin.get("is_active", False):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password."
            )

        if not AdminAuthService.verify_password(password, admin.get("password_hash", "")):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password."
            )

        return AdminAuthService._format_admin(admin)

    @staticmethod
    def get_admin_by_id(admin_id: str) -> dict[str, Any] | None:
        try:
            oid = ObjectId(admin_id)
        except Exception:
            return None

        try:
            admin = db.get_db()["admin_users"].find_one({"_id": oid})
            if admin and admin.get("is_active", False):
                return AdminAuthService._format_admin(admin)
            return None
        except PyMongoError as e:
            logger.error("Database error fetching admin: %s", e)
            return None

    @staticmethod
    def _format_admin(admin: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": str(admin["_id"]),
            "email": admin["email"],
            "name": admin["name"],
            "role": admin["role"],
            "organization_id": str(admin["organization_id"]) if admin.get("organization_id") else None,
            "is_active": admin.get("is_active", True),
            "created_at": admin["created_at"],
        }
