from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
import bcrypt
from fastapi import HTTPException, status
from pymongo.errors import DuplicateKeyError, PyMongoError

from app.db import db

logger = logging.getLogger(__name__)


class OrganizationService:
    @staticmethod
    def hash_join_code(join_code: str) -> str:
        return bcrypt.hashpw(join_code.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    @staticmethod
    def verify_join_code(join_code: str, hashed_code: str) -> bool:
        try:
            return bcrypt.checkpw(join_code.encode("utf-8"), hashed_code.encode("utf-8"))
        except Exception:
            return False

    @staticmethod
    def create_organization(org_id: str, name: str, join_code: str) -> dict[str, Any]:
        import re
        normalized_org_id = org_id.strip().lower()
        if not re.match(r"^[a-z0-9_-]+$", normalized_org_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Organization ID must be alphanumeric and may only contain letters, numbers, hyphens, or underscores."
            )
        hashed_code = OrganizationService.hash_join_code(join_code)
        now = datetime.now(timezone.utc)

        doc = {
            "org_id": normalized_org_id,
            "name": name.strip(),
            "join_code_hash": hashed_code,
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        }

        collection = db.get_db()["organizations"]
        try:
            result = collection.insert_one(doc)
            inserted_id = result.inserted_id
        except DuplicateKeyError:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Organization ID already exists."
            )
        except PyMongoError as e:
            logger.error("Failed to create organization: %s", e)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Unable to create organization at this time."
            )

        created = collection.find_one({"_id": inserted_id})
        if not created:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Unable to verify organization creation."
            )

        return OrganizationService._format_org(created)

    @staticmethod
    def find_organization_by_org_id(org_id: str) -> dict[str, Any] | None:
        normalized_org_id = org_id.strip().lower()
        try:
            org = db.get_db()["organizations"].find_one({"org_id": normalized_org_id})
            if org:
                return OrganizationService._format_org(org)
            return None
        except PyMongoError as e:
            logger.error("Failed to find organization: %s", e)
            return None

    @staticmethod
    def list_organizations() -> list[dict[str, Any]]:
        try:
            orgs = db.get_db()["organizations"].find().sort("name", 1)
            return [OrganizationService._format_org(org) for org in orgs]
        except PyMongoError as e:
            logger.error("Failed to list organizations: %s", e)
            return []

    @staticmethod
    def _format_org(org: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": str(org["_id"]),
            "org_id": org["org_id"],
            "name": org["name"],
            "join_code_hash": org["join_code_hash"],
            "is_active": org.get("is_active", True),
            "created_at": org["created_at"],
            "updated_at": org["updated_at"],
        }
