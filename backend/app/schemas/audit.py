from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from pydantic import BaseModel, Field


class AuditEventType(StrEnum):
    ADMIN_LOGIN = "admin_login"
    ADMIN_LOGIN_FAILED = "admin_login_failed"
    ADMIN_LOGOUT = "admin_logout"
    ORGANIZATION_CREATED = "organization_created"
    ORGANIZATION_JOIN_REQUEST_SUBMITTED = "organization_join_request_submitted"
    ORGANIZATION_JOIN_REQUEST_APPROVED = "organization_join_request_approved"
    ORGANIZATION_JOIN_REQUEST_REJECTED = "organization_join_request_rejected"
    ORGANIZATION_JOIN_FAILED = "organization_join_failed"
    ORGANIZATION_ACCESS_DENIED = "organization_access_denied"
    ORGANIZATION_CONVERSATION_CREATED = "organization_conversation_created"
    ORGANIZATION_CONVERSATION_ACCESS_DENIED = "organization_conversation_access_denied"


class AuditActorType(StrEnum):
    USER = "user"
    ADMIN = "admin"
    SYSTEM = "system"


class AuditAction(StrEnum):
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    APPROVE = "approve"
    REJECT = "reject"
    LOGIN = "login"
    LOGOUT = "logout"
    JOIN = "join"


class AuditStatus(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"


class AuditLogResponse(BaseModel):
    id: str
    event_type: str
    actor_type: str
    actor_id: str | None = None
    actor_role: str | None = None
    organization_id: str | None = None
    target_type: str | None = None
    target_id: str | None = None
    action: str
    status: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    ip_address: str | None = None
    user_agent: str | None = None
    created_at: datetime
