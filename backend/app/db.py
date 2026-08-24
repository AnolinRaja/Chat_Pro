from __future__ import annotations

from typing import Any

from pymongo import ASCENDING, MongoClient
from pymongo.errors import PyMongoError

from app.config import settings


class Database:
    client: MongoClient | None = None

    @classmethod
    def get_client(cls) -> MongoClient:
        if cls.client is None:
            cls.client = MongoClient(settings.MONGODB_URI, serverSelectionTimeoutMS=5000)
        return cls.client

    @classmethod
    def get_db(cls) -> Any:
        client = cls.get_client()
        return client[settings.MONGODB_DB]

    @classmethod
    def ensure_indexes(cls) -> None:
        db = cls.get_db()
        try:
            db["users"].create_index("email", unique=True, name="unique_email_idx")
        except PyMongoError:
            pass
        try:
            db["conversations"].create_index("participants", name="conversations_participants_idx")
        except PyMongoError:
            pass
        try:
            db["conversations"].create_index(
                "participant_key",
                unique=True,
                sparse=True,
                name="unique_conversation_participant_key_idx",
            )
        except PyMongoError:
            pass
        try:
            db["messages"].create_index("conversation_id", name="messages_conversation_id_idx")
        except PyMongoError:
            pass
        try:
            db["messages"].create_index([("conversation_id", ASCENDING), ("created_at", ASCENDING)], name="messages_conversation_created_idx")
        except PyMongoError:
            pass

    @classmethod
    def health_check(cls) -> dict[str, str | bool]:
        try:
            client = cls.get_client()
            client.admin.command("ping")
            return {"connected": True, "database": settings.MONGODB_DB}
        except PyMongoError as exc:
            return {"connected": False, "database": settings.MONGODB_DB, "error": str(exc)}


db = Database()
db.ensure_indexes()
