from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from bson import ObjectId
from fastapi import HTTPException, status
from pymongo.errors import DuplicateKeyError, PyMongoError

from app.db import db
from app.services.organization_membership_service import OrganizationMembershipService

logger = logging.getLogger(__name__)


class OrganizationRequestService:
    @staticmethod
    def create_request(user_id: str, organization_id: str) -> dict[str, Any]:
        try:
            u_oid = ObjectId(user_id)
            o_oid = ObjectId(organization_id)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid user ID or organization ID format."
            )

        collection = db.get_db()["organization_registration_requests"]
        try:
            existing = collection.find_one({"user_id": u_oid, "organization_id": o_oid})
        except PyMongoError as e:
            logger.error("Failed to find request: %s", e)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database error during request check."
            )

        now = datetime.now(timezone.utc)

        if existing:
            current_status = existing.get("status")
            if current_status == "PENDING":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="A pending registration request already exists for this organization."
                )
            elif current_status == "APPROVED":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="You are already an approved member of this organization."
                )
            elif current_status == "REJECTED":
                # Reset request to PENDING
                try:
                    result = collection.find_one_and_update(
                        {"_id": existing["_id"]},
                        {
                            "$set": {
                                "status": "PENDING",
                                "reviewed_by": None,
                                "reviewed_at": None,
                                "updated_at": now,
                            }
                        },
                        return_document=True
                    )
                    return OrganizationRequestService._format_request(result)
                except PyMongoError as e:
                    logger.error("Failed to reset request: %s", e)
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="Unable to resubmit request at this time."
                    )

        # No request exists, create new PENDING request
        doc = {
            "user_id": u_oid,
            "organization_id": o_oid,
            "status": "PENDING",
            "reviewed_by": None,
            "reviewed_at": None,
            "created_at": now,
            "updated_at": now,
        }

        try:
            result = collection.insert_one(doc)
            inserted_id = result.inserted_id
        except DuplicateKeyError:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A registration request already exists for this organization."
            )
        except PyMongoError as e:
            logger.error("Failed to create request: %s", e)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Unable to create request at this time."
            )

        created = collection.find_one({"_id": inserted_id})
        if not created:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Unable to verify request creation."
            )

        return OrganizationRequestService._format_request(created)

    @staticmethod
    def find_request(user_id: str, organization_id: str) -> dict[str, Any] | None:
        try:
            u_oid = ObjectId(user_id)
            o_oid = ObjectId(organization_id)
        except Exception:
            return None

        try:
            request = db.get_db()["organization_registration_requests"].find_one({
                "user_id": u_oid,
                "organization_id": o_oid,
            })
            if request:
                return OrganizationRequestService._format_request(request)
            return None
        except PyMongoError as e:
            logger.error("Failed to find request: %s", e)
            return None

    @staticmethod
    def get_request_by_id(request_id: str) -> dict[str, Any] | None:
        try:
            req_oid = ObjectId(request_id)
        except Exception:
            return None

        try:
            request = db.get_db()["organization_registration_requests"].find_one({"_id": req_oid})
            if request:
                return OrganizationRequestService._format_request(request)
            return None
        except PyMongoError as e:
            logger.error("Failed to find request by id: %s", e)
            return None

    @staticmethod
    def list_requests(
        organization_id: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        query: dict[str, Any] = {}
        if organization_id:
            try:
                query["organization_id"] = ObjectId(organization_id)
            except Exception:
                return []

        if status and status != "ALL":
            query["status"] = status

        try:
            requests = list(db.get_db()["organization_registration_requests"].find(query).sort("created_at", -1))
            return [OrganizationRequestService._format_request(r) for r in requests]
        except PyMongoError as e:
            logger.error("Failed to list requests: %s", e)
            return []

    @staticmethod
    def list_user_requests(user_id: str) -> list[dict[str, Any]]:
        try:
            u_oid = ObjectId(user_id)
        except Exception:
            return []

        try:
            requests = list(db.get_db()["organization_registration_requests"].find({"user_id": u_oid}).sort("created_at", -1))
            result = []
            for r in requests:
                org = db.get_db()["organizations"].find_one({"_id": r["organization_id"]})
                result.append({
                    "id": str(r["_id"]),
                    "organization_id": str(r["organization_id"]),
                    "organization_name": org.get("name", "Unknown") if org else "Unknown",
                    "org_id": org.get("org_id", "") if org else "",
                    "status": r["status"],
                    "created_at": r["created_at"],
                    "updated_at": r["updated_at"],
                })
            return result
        except PyMongoError as e:
            logger.error("Failed to list user requests: %s", e)
            return []

    @staticmethod
    def update_request_status(request_id: str, new_status: str, reviewed_by: str | None = None) -> dict[str, Any]:
        if new_status not in {"PENDING", "APPROVED", "REJECTED"}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid request status."
            )

        try:
            req_oid = ObjectId(request_id)
            rev_oid = ObjectId(reviewed_by) if reviewed_by else None
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid request ID or reviewer ID format."
            )

        collection = db.get_db()["organization_registration_requests"]
        try:
            request = collection.find_one({"_id": req_oid})
        except PyMongoError as e:
            logger.error("Failed to find request to update: %s", e)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database error during request update."
            )

        if not request:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Registration request not found."
            )

        if request.get("status") != "PENDING":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only pending requests can be reviewed."
            )

        now = datetime.now(timezone.utc)
        update_fields = {
            "status": new_status,
            "reviewed_by": rev_oid,
            "reviewed_at": now,
            "updated_at": now,
        }

        try:
            updated = collection.find_one_and_update(
                {"_id": req_oid},
                {"$set": update_fields},
                return_document=True
            )
        except PyMongoError as e:
            logger.error("Failed to update request status: %s", e)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Unable to update request status at this time."
            )

        # If status transitioned to APPROVED, automatically create the membership
        if new_status == "APPROVED":
            OrganizationMembershipService.create_membership(
                user_id=str(updated["user_id"]),
                organization_id=str(updated["organization_id"]),
                role="member"
            )

        return OrganizationRequestService._format_request(updated)

    @staticmethod
    def _format_request(request: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": str(request["_id"]),
            "user_id": str(request["user_id"]),
            "organization_id": str(request["organization_id"]),
            "status": request["status"],
            "reviewed_by": str(request["reviewed_by"]) if request.get("reviewed_by") else None,
            "reviewed_at": request.get("reviewed_at"),
            "created_at": request["created_at"],
            "updated_at": request["updated_at"],
        }
