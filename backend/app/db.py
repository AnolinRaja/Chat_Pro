from __future__ import annotations

import logging
from typing import Any

from pymongo import ASCENDING, MongoClient
from pymongo.errors import PyMongoError

from app.config import settings

logger = logging.getLogger(__name__)


class Database:
    client: MongoClient | None = None
    EXPECTED_INDEXES = (
        {
            "collection": "users",
            "name": "unique_email_idx",
            "keys": [("email", ASCENDING)],
            "options": {"unique": True},
        },
        {
            "collection": "conversations",
            "name": "conversations_participants_idx",
            "keys": [("participants", ASCENDING)],
            "options": {},
        },
        {
            "collection": "conversations",
            "name": "unique_conversation_participant_key_idx",
            "keys": [("participant_key", ASCENDING)],
            "options": {"unique": True, "sparse": True},
        },
        {
            "collection": "messages",
            "name": "messages_conversation_id_idx",
            "keys": [("conversation_id", ASCENDING)],
            "options": {},
        },
        {
            "collection": "messages",
            "name": "messages_conversation_created_idx",
            "keys": [("conversation_id", ASCENDING), ("created_at", ASCENDING)],
            "options": {},
        },
        {
            "collection": "messages",
            "name": "messages_conversation_created_id_idx",
            "keys": [
                ("conversation_id", ASCENDING),
                ("created_at", ASCENDING),
                ("_id", ASCENDING),
            ],
            "options": {},
        },
    )

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
    def ensure_indexes(cls) -> dict[str, dict[str, list[str]]]:
        database = cls.get_db()
        for index in cls.EXPECTED_INDEXES:
            try:
                database[index["collection"]].create_index(
                    index["keys"],
                    name=index["name"],
                    **index["options"],
                )
            except PyMongoError:
                logger.error(
                    "Failed to create MongoDB index collection=%s index=%s",
                    index["collection"],
                    index["name"],
                )

        return cls.verify_indexes(database)

    @classmethod
    def verify_indexes(cls, database: Any | None = None) -> dict[str, dict[str, list[str]]]:
        if database is None:
            database = cls.get_db()
        verification: dict[str, dict[str, list[str]]] = {}
        expected_by_collection: dict[str, list[str]] = {}
        for index in cls.EXPECTED_INDEXES:
            expected_by_collection.setdefault(index["collection"], []).append(index["name"])

        for collection_name, expected_names in expected_by_collection.items():
            present_names: set[str] = set()
            try:
                present_names = {
                    index["name"] for index in database[collection_name].list_indexes()
                }
            except PyMongoError:
                logger.error(
                    "Failed to verify MongoDB indexes collection=%s",
                    collection_name,
                )

            verification[collection_name] = {
                "present": [name for name in expected_names if name in present_names],
                "missing": [name for name in expected_names if name not in present_names],
            }

        return verification

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
