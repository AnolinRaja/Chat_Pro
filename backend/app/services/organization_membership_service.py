from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from bson import ObjectId
from fastapi import HTTPException, status
from pymongo.errors import DuplicateKeyError, PyMongoError

from app.db import db

logger = logging.getLogger(__name__)


class OrganizationMembershipService:
    @staticmethod
    def create_membership(user_id: str, organization_id: str, role: str = "member") -> dict[str, Any]:
        if role not in {"member", "org_admin"}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid membership role."
            )

        try:
            u_oid = ObjectId(user_id)
            o_oid = ObjectId(organization_id)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid user ID or organization ID format."
            )

        now = datetime.now(timezone.utc)
        doc = {
            "user_id": u_oid,
            "organization_id": o_oid,
            "role": role,
            "created_at": now,
        }

        collection = db.get_db()["organization_memberships"]
        try:
            result = collection.insert_one(doc)
            inserted_id = result.inserted_id
        except DuplicateKeyError:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="User is already a member of this organization."
            )
        except PyMongoError as e:
            logger.error("Failed to create membership: %s", e)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Unable to create membership at this time."
            )

        created = collection.find_one({"_id": inserted_id})
        if not created:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Unable to verify membership creation."
            )

        return OrganizationMembershipService._format_membership(created)

    @staticmethod
    def find_membership(user_id: str, organization_id: str) -> dict[str, Any] | None:
        try:
            u_oid = ObjectId(user_id)
            o_oid = ObjectId(organization_id)
        except Exception:
            return None

        try:
            member = db.get_db()["organization_memberships"].find_one({
                "user_id": u_oid,
                "organization_id": o_oid,
            })
            if member:
                return OrganizationMembershipService._format_membership(member)
            return None
        except PyMongoError as e:
            logger.error("Failed to find membership: %s", e)
            return None

    @staticmethod
    def check_membership(user_id: str, organization_id: str) -> bool:
        return bool(OrganizationMembershipService.find_membership(user_id, organization_id))

    @staticmethod
    def list_organization_members(organization_id: str) -> list[dict[str, Any]]:
        try:
            o_oid = ObjectId(organization_id)
        except Exception:
            return []

        try:
            members = list(db.get_db()["organization_memberships"].find({"organization_id": o_oid}).sort("created_at", 1))
            result = []
            for m in members:
                user = db.get_db()["users"].find_one({"_id": m["user_id"]})
                result.append({
                    "membership_id": str(m["_id"]),
                    "user_id": str(m["user_id"]),
                    "name": user.get("name", "Unknown") if user else "Unknown",
                    "email": user.get("email", "") if user else "",
                    "role": m.get("role", "member"),
                    "created_at": m["created_at"],
                })
            return result
        except PyMongoError as e:
            logger.error("Failed to list organization members: %s", e)
            return []

    @staticmethod
    def list_user_memberships(user_id: str) -> list[dict[str, Any]]:
        try:
            u_oid = ObjectId(user_id)
        except Exception:
            return []

        try:
            members = list(db.get_db()["organization_memberships"].find({"user_id": u_oid}).sort("created_at", 1))
            result = []
            for m in members:
                org = db.get_db()["organizations"].find_one({"_id": m["organization_id"]})
                result.append({
                    "id": str(m["_id"]),
                    "organization_id": str(m["organization_id"]),
                    "organization_name": org.get("name", "Unknown") if org else "Unknown",
                    "org_id": org.get("org_id", "") if org else "",
                    "role": m.get("role", "member"),
                    "created_at": m["created_at"],
                })
            return result
        except PyMongoError as e:
            logger.error("Failed to list user memberships: %s", e)
            return []

    @staticmethod
    def _format_membership(member: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": str(member["_id"]),
            "user_id": str(member["user_id"]),
            "organization_id": str(member["organization_id"]),
            "role": member["role"],
            "created_at": member["created_at"],
        }
