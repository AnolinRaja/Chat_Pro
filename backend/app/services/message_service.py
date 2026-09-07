from __future__ import annotations

import base64
import binascii
import json
import logging
from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from fastapi import HTTPException
from pymongo.errors import PyMongoError

from app.db import db
from app.services.conversation_service import ConversationService

logger = logging.getLogger(__name__)


class MessageService:
    ACTIVITY_UPDATE_ATTEMPTS = 3
    DEFAULT_MESSAGE_LIMIT = 50
    MAX_MESSAGE_LIMIT = 100

    @staticmethod
    def send_message(conversation_id: str, user_id: str, content: str) -> dict[str, Any]:
        content = content.strip()
        if not content:
            raise HTTPException(status_code=400, detail="Message content cannot be empty.")

        if len(content) > 5000:
            raise HTTPException(status_code=400, detail="Message content exceeds maximum length.")

        conversation = ConversationService.get_authorized_conversation(conversation_id, user_id)
        conv_oid = conversation["_id"]
        user_oid = ObjectId(user_id)

        now = datetime.now(timezone.utc)
        msg_doc = {
            "conversation_id": conv_oid,
            "sender_id": user_oid,
            "content": content,
            "created_at": now,
        }

        messages_collection = db.get_db()["messages"]
        conversations_collection = db.get_db()["conversations"]
        try:
            result = messages_collection.insert_one(msg_doc)
        except PyMongoError:
            raise HTTPException(status_code=500, detail="Unable to send message.")

        msg_id_str = str(result.inserted_id)
        latest_message_doc = {
            "id": msg_id_str,
            "content": content[:200],
            "sender_id": user_id,
            "created_at": now,
        }

        for attempt in range(MessageService.ACTIVITY_UPDATE_ATTEMPTS):
            try:
                conversations_collection.update_one(
                    {
                        "_id": conv_oid,
                        "$or": [
                            {"latest_message.created_at": {"$lt": now}},
                            {"latest_message.created_at": now, "latest_message.id": {"$lt": msg_id_str}},
                            {"latest_message": {"$exists": False}},
                        ],
                    },
                    {
                        "$set": {
                            "updated_at": now,
                            "latest_message": latest_message_doc,
                        }
                    },
                )
                break
            except PyMongoError:
                if attempt == MessageService.ACTIVITY_UPDATE_ATTEMPTS - 1:
                    logger.exception(
                        "Unable to update conversation activity after %s attempts for conversation_id=%s",
                        MessageService.ACTIVITY_UPDATE_ATTEMPTS,
                        conversation_id,
                    )

        created = messages_collection.find_one({"_id": result.inserted_id})
        if created is None:
            raise HTTPException(status_code=500, detail="Unable to send message.")

        return MessageService._format_message(created)

    @staticmethod
    def calculate_unread_count(conv_oid: ObjectId, user_oid: ObjectId, read_at: datetime | None, read_msg_oid: ObjectId | None) -> int:
        if read_at is None or read_msg_oid is None:
            return 0
        messages_collection = db.get_db()["messages"]
        query = {
            "conversation_id": conv_oid,
            "sender_id": {"$ne": user_oid},
            "$or": [
                {"created_at": {"$gt": read_at}},
                {"created_at": read_at, "_id": {"$gt": read_msg_oid}},
            ],
        }
        return messages_collection.count_documents(query)

    @staticmethod
    def calculate_unread_counts_batch(conv_read_map: dict[ObjectId, tuple[datetime | None, ObjectId | None]], user_oid: ObjectId) -> dict[ObjectId, int]:
        unread_map: dict[ObjectId, int] = {conv_oid: 0 for conv_oid in conv_read_map}
        match_conditions = []

        for conv_oid, (read_at, read_msg_id) in conv_read_map.items():
            if read_at is not None and read_msg_id is not None:
                match_conditions.append({
                    "conversation_id": conv_oid,
                    "sender_id": {"$ne": user_oid},
                    "$or": [
                        {"created_at": {"$gt": read_at}},
                        {"created_at": read_at, "_id": {"$gt": read_msg_id}},
                    ],
                })
            else:
                match_conditions.append({
                    "conversation_id": conv_oid,
                    "sender_id": {"$ne": user_oid},
                })

        if not match_conditions:
            return unread_map

        pipeline = [
            {"$match": {"$or": match_conditions}},
            {"$group": {"_id": "$conversation_id", "unread_count": {"$sum": 1}}},
        ]

        try:
            results = list(db.get_db()["messages"].aggregate(pipeline))
            for doc in results:
                unread_map[doc["_id"]] = doc["unread_count"]
        except PyMongoError as e:
            logger.error("Failed to execute batched unread aggregation: %s", e)

        return unread_map


    @staticmethod
    def get_messages(
        conversation_id: str,
        user_id: str,
        limit: int = DEFAULT_MESSAGE_LIMIT,
        cursor: str | None = None,
    ) -> list[dict[str, Any]]:
        messages, _ = MessageService.get_messages_page(conversation_id, user_id, limit, cursor)
        return messages

    @staticmethod
    def get_messages_page(
        conversation_id: str,
        user_id: str,
        limit: int = DEFAULT_MESSAGE_LIMIT,
        cursor: str | None = None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        if not 1 <= limit <= MessageService.MAX_MESSAGE_LIMIT:
            raise HTTPException(status_code=400, detail="Message limit must be between 1 and 100.")

        conversation = ConversationService.get_authorized_conversation(conversation_id, user_id)
        conv_oid = conversation["_id"]

        messages_collection = db.get_db()["messages"]
        message_filter: dict[str, Any] = {"conversation_id": conv_oid}
        if cursor is not None:
            cursor_time, cursor_id = MessageService._decode_message_cursor(cursor)
            message_filter["$or"] = [
                {"created_at": {"$gt": cursor_time}},
                {"created_at": cursor_time, "_id": {"$gt": cursor_id}},
            ]

        messages = list(
            messages_collection.find(message_filter)
            .sort([("created_at", 1), ("_id", 1)])
            .limit(limit + 1)
        )
        has_next_page = len(messages) > limit
        messages = messages[:limit]
        formatted_messages = [MessageService._format_message(msg) for msg in messages]
        next_cursor = (
            MessageService._encode_message_cursor(messages[-1])
            if has_next_page and messages
            else None
        )

        return formatted_messages, next_cursor

    @staticmethod
    def _encode_message_cursor(message: dict[str, Any]) -> str:
        cursor = {
            "created_at": message["created_at"].isoformat(),
            "id": str(message["_id"]),
        }
        encoded = json.dumps(cursor, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(encoded).decode("ascii").rstrip("=")

    @staticmethod
    def _decode_message_cursor(cursor: str) -> tuple[datetime, ObjectId]:
        try:
            padding = "=" * (-len(cursor) % 4)
            decoded = base64.urlsafe_b64decode(cursor + padding).decode("utf-8")
            value = json.loads(decoded)
            cursor_time = datetime.fromisoformat(value["created_at"])
            cursor_id = ObjectId(value["id"])
        except (
            ValueError,
            TypeError,
            KeyError,
            json.JSONDecodeError,
            UnicodeDecodeError,
            binascii.Error,
        ):
            raise HTTPException(status_code=400, detail="Invalid message cursor.")

        if cursor_time.tzinfo is None:
            cursor_time = cursor_time.replace(tzinfo=timezone.utc)
        return cursor_time, cursor_id

    @staticmethod
    def _format_message(doc: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": str(doc["_id"]),
            "conversation_id": str(doc["conversation_id"]),
            "sender_id": str(doc["sender_id"]),
            "content": doc["content"],
            "created_at": doc["created_at"],
        }
