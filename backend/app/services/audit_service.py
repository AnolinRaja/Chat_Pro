from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from bson import ObjectId
from fastapi import Request
from pymongo.errors import PyMongoError

from app.db import db
from app.schemas.audit import AuditAction, AuditActorType, AuditEventType, AuditStatus

logger = logging.getLogger(__name__)

FORBIDDEN_KEY_PATTERNS = {
    "password",
    "password_hash",
    "join_code",
    "join_code_hash",
    "refresh_token",
    "access_token",
    "jwt",
    "token",
    "otp",
    "otp_hash",
    "cookie",
    "authorization",
    "session_token",
    "secret",
}


class AuditService:
    @staticmethod
    def _is_forbidden_key(key: str) -> bool:
        k = key.lower()
        return any(pattern in k for pattern in FORBIDDEN_KEY_PATTERNS)

    @staticmethod
    def _sanitize_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
        if not metadata or not isinstance(metadata, dict):
            return {}

        clean: dict[str, Any] = {}
        for key, value in metadata.items():
            if AuditService._is_forbidden_key(key):
                continue

            if isinstance(value, dict):
                clean[key] = AuditService._sanitize_metadata(value)
            elif isinstance(value, list):
                clean[key] = [
                    AuditService._sanitize_metadata(item) if isinstance(item, dict) else (str(item) if isinstance(item, ObjectId) else item)
                    for item in value
                ]
            elif isinstance(value, ObjectId):
                clean[key] = str(value)
            else:
                clean[key] = value

        return clean

    @staticmethod
    def extract_request_context(request: Request | None) -> tuple[str | None, str | None]:
        if request is None:
            return None, None
        ip_address = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent")
        return ip_address, user_agent

    @staticmethod
    def log_event(
        event_type: str | AuditEventType,
        actor_type: str | AuditActorType,
        action: str | AuditAction,
        status: str | AuditStatus = AuditStatus.SUCCESS,
        actor_id: str | ObjectId | None = None,
        actor_role: str | None = None,
        organization_id: str | ObjectId | None = None,
        target_type: str | None = None,
        target_id: str | ObjectId | None = None,
        metadata: dict[str, Any] | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> dict[str, Any] | None:
        try:
            act_oid = ObjectId(actor_id) if actor_id and isinstance(actor_id, str) and ObjectId.is_valid(actor_id) else (actor_id if isinstance(actor_id, ObjectId) else None)
            org_oid = ObjectId(organization_id) if organization_id and isinstance(organization_id, str) and ObjectId.is_valid(organization_id) else (organization_id if isinstance(organization_id, ObjectId) else None)
            tgt_oid = ObjectId(target_id) if target_id and isinstance(target_id, str) and ObjectId.is_valid(target_id) else (target_id if isinstance(target_id, ObjectId) else None)

            clean_meta = AuditService._sanitize_metadata(metadata)
            now = datetime.now(timezone.utc)

            doc = {
                "event_type": str(event_type.value if hasattr(event_type, "value") else event_type),
                "actor_type": str(actor_type.value if hasattr(actor_type, "value") else actor_type),
                "actor_id": act_oid,
                "actor_role": actor_role,
                "organization_id": org_oid,
                "target_type": target_type,
                "target_id": tgt_oid,
                "action": str(action.value if hasattr(action, "value") else action),
                "status": str(status.value if hasattr(status, "value") else status),
                "metadata": clean_meta,
                "ip_address": ip_address,
                "user_agent": user_agent,
                "created_at": now,
            }

            collection = db.get_db()["audit_logs"]
            result = collection.insert_one(doc)
            doc["_id"] = result.inserted_id
            return AuditService._format_audit_log(doc)
        except PyMongoError as e:
            logger.warning("Database error during audit logging: %s", e)
            return None
        except Exception as e:
            logger.warning("Unexpected error during audit logging: %s", e)
            return None

    @staticmethod
    def list_events(
        organization_id: str | None = None,
        actor_id: str | None = None,
        event_type: str | None = None,
        status: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        query: dict[str, Any] = {}

        if organization_id:
            try:
                query["organization_id"] = ObjectId(organization_id)
            except Exception:
                return []

        if actor_id:
            try:
                query["actor_id"] = ObjectId(actor_id)
            except Exception:
                return []

        if event_type:
            query["event_type"] = event_type

        if status:
            query["status"] = status

        if start_date or end_date:
            date_filter: dict[str, Any] = {}
            if start_date:
                sd = start_date
                if isinstance(sd, str):
                    try:
                        sd = datetime.fromisoformat(sd.replace("Z", "+00:00"))
                    except Exception:
                        sd = None
                if sd:
                    date_filter["$gte"] = sd if sd.tzinfo else sd.replace(tzinfo=timezone.utc)
            if end_date:
                ed = end_date
                if isinstance(ed, str):
                    try:
                        ed = datetime.fromisoformat(ed.replace("Z", "+00:00"))
                    except Exception:
                        ed = None
                if ed:
                    date_filter["$lte"] = ed if ed.tzinfo else ed.replace(tzinfo=timezone.utc)
            if date_filter:
                query["created_at"] = date_filter

        safe_limit = max(1, min(limit, 100))

        try:
            cursor = db.get_db()["audit_logs"].find(query).sort([("created_at", -1), ("_id", -1)]).limit(safe_limit)
            return [AuditService._format_audit_log(doc) for doc in cursor]
        except PyMongoError as e:
            logger.error("Failed to query audit logs: %s", e)
            return []

    @staticmethod
    def _format_audit_log(doc: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": str(doc["_id"]),
            "event_type": doc["event_type"],
            "actor_type": doc["actor_type"],
            "actor_id": str(doc["actor_id"]) if doc.get("actor_id") else None,
            "actor_role": doc.get("actor_role"),
            "organization_id": str(doc["organization_id"]) if doc.get("organization_id") else None,
            "target_type": doc.get("target_type"),
            "target_id": str(doc["target_id"]) if doc.get("target_id") else None,
            "action": doc["action"],
            "status": doc["status"],
            "metadata": doc.get("metadata", {}),
            "ip_address": doc.get("ip_address"),
            "user_agent": doc.get("user_agent"),
            "created_at": doc["created_at"],
        }
