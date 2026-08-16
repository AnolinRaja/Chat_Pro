from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from fastapi import HTTPException
from pymongo.errors import PyMongoError

from app.db import db


class ConversationService:
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

        existing = conversations_collection.find_one({"participants": {"$all": sorted_participants}})
        if existing:
            return ConversationService._format_conversation(existing)

        now = datetime.now(timezone.utc)
        doc = {
            "participants": sorted_participants,
            "created_at": now,
            "updated_at": now,
        }

        try:
            result = conversations_collection.insert_one(doc)
        except PyMongoError:
            raise HTTPException(status_code=500, detail="Unable to create conversation.")

        created = conversations_collection.find_one({"_id": result.inserted_id})
        if created is None:
            raise HTTPException(status_code=500, detail="Unable to create conversation.")

        return ConversationService._format_conversation(created)

    @staticmethod
    def list_conversations(user_id: str) -> list[dict[str, Any]]:
        try:
            user_oid = ObjectId(user_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid user ID format.")

        conversations_collection = db.get_db()["conversations"]
        conversations = list(conversations_collection.find({"participants": user_oid}).sort("updated_at", -1))

        return [ConversationService._format_conversation(conv) for conv in conversations]

    @staticmethod
    def get_conversation(conversation_id: str, user_id: str) -> dict[str, Any]:
        try:
            conv_oid = ObjectId(conversation_id)
            user_oid = ObjectId(user_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid ID format.")

        conversations_collection = db.get_db()["conversations"]
        conversation = conversations_collection.find_one({"_id": conv_oid})

        if conversation is None:
            raise HTTPException(status_code=404, detail="Conversation not found.")

        if user_oid not in conversation.get("participants", []):
            raise HTTPException(status_code=403, detail="Access denied.")

        return ConversationService._format_conversation(conversation)

    @staticmethod
    def _format_conversation(doc: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": str(doc["_id"]),
            "participants": [str(p) for p in doc["participants"]],
            "created_at": doc["created_at"],
            "updated_at": doc["updated_at"],
        }
