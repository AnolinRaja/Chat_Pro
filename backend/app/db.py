from __future__ import annotations

import logging
from typing import Any

from pymongo import ASCENDING, MongoClient
from pymongo.errors import PyMongoError

from app.config import settings

logger = logging.getLogger(__name__)


class Database:
    client: MongoClient | None = None
    _available: bool | None = None
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
    def close_client(cls) -> None:
        client = cls.client
        cls.client = None
        cls._available = None
        if client is None:
            return

        try:
            client.close()
            logger.info("MongoDB client closed cleanly")
        except Exception:
            logger.warning("MongoDB client shutdown failed")

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
            actual_indexes: dict[str, Any] = {}
            try:
                actual_indexes = {
                    index["name"]: index
                    for index in database[collection_name].list_indexes()
                }
            except PyMongoError:
                logger.error(
                    "Failed to verify MongoDB indexes collection=%s",
                    collection_name,
                )

            present_names: list[str] = []
            missing_names: list[str] = []
            misconfigured_names: list[str] = []
            for index in cls.EXPECTED_INDEXES:
                if index["collection"] != collection_name:
                    continue

                actual_index = actual_indexes.get(index["name"])
                if actual_index is None:
                    missing_names.append(index["name"])
                elif cls._index_matches(index, actual_index):
                    present_names.append(index["name"])
                else:
                    misconfigured_names.append(index["name"])
                    logger.error(
                        "Misconfigured MongoDB index collection=%s index=%s",
                        collection_name,
                        index["name"],
                    )

            verification[collection_name] = {
                "present": present_names,
                "missing": missing_names,
                "misconfigured": misconfigured_names,
            }

        return verification

    @staticmethod
    def _index_matches(expected: dict[str, Any], actual: dict[str, Any]) -> bool:
        actual_keys = list(actual.get("key", {}).items())
        if actual_keys != expected["keys"]:
            return False

        return all(
            actual.get(option_name) == option_value
            for option_name, option_value in expected["options"].items()
        )

    @classmethod
    def health_check(cls) -> dict[str, str | bool]:
        try:
            client = cls.get_client()
            client.admin.command("ping")
            cls._record_availability(True)
            return {"connected": True, "database": settings.MONGODB_DB}
        except Exception:
            cls._record_availability(False)
            logger.warning("MongoDB health check failed database=%s", settings.MONGODB_DB)
            return {"connected": False, "database": settings.MONGODB_DB}

    @classmethod
    def _record_availability(cls, available: bool) -> None:
        if cls._available == available:
            return

        cls._available = available
        state = "available" if available else "unavailable"
        logger.info("MongoDB availability changed state=%s", state)

    @classmethod
    def get_readiness_status(cls) -> dict[str, Any]:
        database_name = settings.MONGODB_DB
        try:
            client = cls.get_client()
            client.admin.command("ping")
            connected = True
        except Exception:
            cls._record_availability(False)
            logger.warning("MongoDB readiness check failed database=%s", database_name)
            return {"ready": False, "connected": False, "database": database_name, "indexes": {}}

        try:
            database = client[database_name]
            verification = cls.verify_indexes(database)
        except Exception:
            cls._record_availability(False)
            logger.warning("MongoDB readiness could not verify indexes database=%s", database_name)
            return {"ready": False, "connected": True, "database": database_name, "indexes": {}}

        has_missing = any(bool(details["missing"]) for details in verification.values())
        has_misconfigured = any(bool(details["misconfigured"]) for details in verification.values())
        ready = not has_missing and not has_misconfigured
        cls._record_availability(ready)

        if ready:
            logger.info("MongoDB readiness check passed database=%s", database_name)
        else:
            logger.warning("MongoDB readiness check failed database=%s", database_name)

        return {
            "ready": ready,
            "connected": connected,
            "database": database_name,
            "indexes": verification,
        }


db = Database()
db.ensure_indexes()
