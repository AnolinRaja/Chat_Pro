from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from fastapi import HTTPException
from pymongo.errors import PyMongoError

from app.db import db


class MessageService:
    @staticmethod
    def send_message(conversation_id: str, user_id: str, content: str) -> dict[str, Any]:
        try:
            conv_oid = ObjectId(conversation_id)
            user_oid = ObjectId(user_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid ID format.")

        content = content.strip()
        if not content:
            raise HTTPException(status_code=400, detail="Message content cannot be empty.")

        if len(content) > 5000:
            raise HTTPException(status_code=400, detail="Message content exceeds maximum length.")

        conversations_collection = db.get_db()["conversations"]
        conversation = conversations_collection.find_one({"_id": conv_oid})

        if conversation is None:
            raise HTTPException(status_code=404, detail="Conversation not found.")

        if user_oid not in conversation.get("participants", []):
            raise HTTPException(status_code=403, detail="Access denied.")

        now = datetime.now(timezone.utc)
        msg_doc = {
            "conversation_id": conv_oid,
            "sender_id": user_oid,
            "content": content,
            "created_at": now,
        }

        messages_collection = db.get_db()["messages"]
        try:
            result = messages_collection.insert_one(msg_doc)
        except PyMongoError:
            raise HTTPException(status_code=500, detail="Unable to send message.")

        try:
            conversations_collection.update_one({"_id": conv_oid}, {"$set": {"updated_at": now}})
        except PyMongoError:
            pass

        created = messages_collection.find_one({"_id": result.inserted_id})
        if created is None:
            raise HTTPException(status_code=500, detail="Unable to send message.")

        return MessageService._format_message(created)

    @staticmethod
    def get_messages(conversation_id: str, user_id: str) -> list[dict[str, Any]]:
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

        messages_collection = db.get_db()["messages"]
        messages = list(messages_collection.find({"conversation_id": conv_oid}).sort("created_at", 1))

        return [MessageService._format_message(msg) for msg in messages]

    @staticmethod
    def _format_message(doc: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": str(doc["_id"]),
            "conversation_id": str(doc["conversation_id"]),
            "sender_id": str(doc["sender_id"]),
            "content": doc["content"],
            "created_at": doc["created_at"],
        }
