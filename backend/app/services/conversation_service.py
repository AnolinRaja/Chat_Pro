from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from fastapi import HTTPException, status
from pymongo.errors import DuplicateKeyError, PyMongoError

from app.db import db
from app.services.organization_membership_service import OrganizationMembershipService


class ConversationService:
    @staticmethod
    def canonical_participant_key(user_id: str, other_user_id: str) -> str:
        return ":".join(sorted((user_id, other_user_id)))

    @staticmethod
    def create_conversation(user_id: str, other_user_id: str) -> dict[str, Any]:
        if user_id == other_user_id:
            raise HTTPException(status_code=400, detail="Cannot create conversation with yourself.")

        try:
            user_oid = ObjectId(user_id)
            other_oid = ObjectId(other_user_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid user ID format.")

        users_collection = db.get_db()["users"]
        other_user = users_collection.find_one({"_id": other_oid})
        if other_user is None:
            raise HTTPException(status_code=404, detail="User not found.")

        conversations_collection = db.get_db()["conversations"]

        sorted_participants = sorted([user_oid, other_oid], key=lambda x: str(x))
        participant_key = ConversationService.canonical_participant_key(
            str(user_oid),
            str(other_oid),
        )

        existing = conversations_collection.find_one({"participant_key": participant_key})
        if existing is None:
            existing = conversations_collection.find_one({"participants": {"$all": sorted_participants}})
        if existing:
            return ConversationService._format_conversation(existing, user_id)

        now = datetime.now(timezone.utc)
        doc = {
            "type": "direct",
            "participants": sorted_participants,
            "participant_key": participant_key,
            "created_at": now,
            "updated_at": now,
        }

        try:
            result = conversations_collection.insert_one(doc)
        except DuplicateKeyError:
            existing = conversations_collection.find_one({"participant_key": participant_key})
            if existing is not None:
                return ConversationService._format_conversation(existing, user_id)
            raise HTTPException(status_code=500, detail="Unable to create conversation.")
        except PyMongoError:
            raise HTTPException(status_code=500, detail="Unable to create conversation.")

        created = conversations_collection.find_one({"_id": result.inserted_id})
        if created is None:
            raise HTTPException(status_code=500, detail="Unable to create conversation.")

        return ConversationService._format_conversation(created, user_id)

    @staticmethod
    def create_organization_conversation(
        organization_id: str,
        name: str,
        description: str | None = None,
        created_by: str | None = None,
    ) -> dict[str, Any]:
        try:
            org_oid = ObjectId(organization_id)
        except Exception:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid organization ID format.")

        org = db.get_db()["organizations"].find_one({"_id": org_oid})
        if not org:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found.")

        if not org.get("is_active", True):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Organization is inactive.")

        creator_oid: ObjectId | None = None
        if created_by:
            try:
                creator_oid = ObjectId(created_by)
            except Exception:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid creator user ID format.")

            if not OrganizationMembershipService.check_membership(created_by, organization_id):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied: active organization membership required.",
                )

        clean_name = name.strip().lower()
        clean_description = description.strip() if description and description.strip() else None

        now = datetime.now(timezone.utc)
        doc = {
            "type": "organization",
            "organization_id": org_oid,
            "name": clean_name,
            "description": clean_description,
            "created_by": creator_oid,
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        }

        collection = db.get_db()["conversations"]
        try:
            result = collection.insert_one(doc)
        except DuplicateKeyError:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A channel with this name already exists in this organization.",
            )
        except PyMongoError:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Unable to create channel at this time.",
            )

        created = collection.find_one({"_id": result.inserted_id})
        if not created:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Unable to verify channel creation.",
            )

        return ConversationService._format_organization_conversation(created)

    @staticmethod
    def list_organization_conversations(organization_id: str) -> list[dict[str, Any]]:
        try:
            org_oid = ObjectId(organization_id)
        except Exception:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid organization ID format.")

        org = db.get_db()["organizations"].find_one({"_id": org_oid})
        if not org:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found.")

        if not org.get("is_active", True):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Organization is inactive.")

        collection = db.get_db()["conversations"]
        cursor = collection.find({
            "organization_id": org_oid,
            "type": "organization",
            "is_active": {"$ne": False},
        }).sort([("updated_at", -1), ("name", 1)])

        return [ConversationService._format_organization_conversation(doc) for doc in cursor]

    @staticmethod
    def list_conversations(user_id: str) -> list[dict[str, Any]]:
        try:
            user_oid = ObjectId(user_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid user ID format.")

        conversations_collection = db.get_db()["conversations"]
        conversations = list(conversations_collection.find({"participants": user_oid}).sort("updated_at", -1))

        return [ConversationService._format_conversation(conv, user_id) for conv in conversations]

    @staticmethod
    def get_authorized_conversation(conversation_id: str, user_id: str) -> dict[str, Any]:
        try:
            conv_oid = ObjectId(conversation_id)
            user_oid = ObjectId(user_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid ID format.")

        conversations_collection = db.get_db()["conversations"]
        conversation = conversations_collection.find_one({"_id": conv_oid})

        if conversation is None:
            raise HTTPException(status_code=404, detail="Conversation not found.")

        if conversation.get("type") == "organization" or conversation.get("organization_id") is not None:
            org_oid = conversation.get("organization_id")
            org = db.get_db()["organizations"].find_one({"_id": org_oid})
            if not org:
                raise HTTPException(status_code=404, detail="Organization not found.")

            if not org.get("is_active", True):
                raise HTTPException(status_code=403, detail="Organization is inactive.")

            if not OrganizationMembershipService.check_membership(user_id, str(org_oid)):
                raise HTTPException(status_code=403, detail="Access denied: active organization membership required.")

            return conversation

        # Direct conversation
        if user_oid not in conversation.get("participants", []):
            raise HTTPException(status_code=403, detail="Access denied.")

        return conversation

    @staticmethod
    def get_conversation(conversation_id: str, user_id: str) -> dict[str, Any]:
        conversation = ConversationService.get_authorized_conversation(conversation_id, user_id)
        if conversation.get("type") == "organization" or conversation.get("organization_id") is not None:
            return ConversationService._format_organization_conversation(conversation)
        return ConversationService._format_conversation(conversation, user_id)

    @staticmethod
    def _format_conversation(doc: dict[str, Any], user_id: str) -> dict[str, Any]:
        participant_ids = [str(participant) for participant in (doc.get("participants") or [])]
        other_user_id = next(
            (participant_id for participant_id in participant_ids if participant_id != user_id),
            participant_ids[0] if participant_ids else "",
        )
        other_user = db.get_db()["users"].find_one(
            {"_id": ObjectId(other_user_id)},
            {"name": 1, "email": 1},
        ) if other_user_id else None

        return {
            "id": str(doc["_id"]),
            "participants": participant_ids,
            "other_user": {
                "id": other_user_id,
                "name": other_user.get("name", "") if other_user else "",
                "email": other_user.get("email", "") if other_user else "",
            },
            "created_at": doc["created_at"],
            "updated_at": doc["updated_at"],
        }

    @staticmethod
    def _format_organization_conversation(doc: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": str(doc["_id"]),
            "type": "organization",
            "organization_id": str(doc["organization_id"]),
            "name": doc["name"],
            "description": doc.get("description"),
            "created_by": str(doc["created_by"]) if doc.get("created_by") else None,
            "is_active": doc.get("is_active", True),
            "created_at": doc["created_at"],
            "updated_at": doc["updated_at"],
        }
