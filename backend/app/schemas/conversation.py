from __future__ import annotations

import re
from datetime import datetime
from pydantic import BaseModel, Field, field_validator


class ConversationCreate(BaseModel):
    other_user_id: str = Field(..., min_length=1)


class ConversationUser(BaseModel):
    id: str
    name: str
    email: str


class ConversationResponse(BaseModel):
    id: str
    participants: list[str]
    other_user: ConversationUser
    created_at: datetime
    updated_at: datetime


class OrganizationConversationCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    description: str | None = Field(None, max_length=500)

    @field_validator("name")
    @classmethod
    def validate_channel_name(cls, v: str) -> str:
        name = v.strip().lower()
        if not name:
            raise ValueError("Channel name cannot be empty.")
        if not re.match(r"^[a-z0-9-]+$", name):
            raise ValueError("Channel name must contain only lowercase alphanumeric characters and hyphens.")
        return name

    @field_validator("description")
    @classmethod
    def validate_description(cls, v: str | None) -> str | None:
        if v is None:
            return None
        s = v.strip()
        return s if s else None


class OrganizationConversationResponse(BaseModel):
    id: str
    type: str = "organization"
    organization_id: str
    name: str
    description: str | None = None
    created_by: str | None = None
    is_active: bool = True
    created_at: datetime
    updated_at: datetime


class MessageCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=5000)

    class Config:
        json_schema_extra = {
            "example": {"content": "Hello!"}
        }

    def __init__(self, **data):
        super().__init__(**data)
        self.content = self.content.strip()
        if not self.content:
            raise ValueError("Content cannot be empty or whitespace-only.")


class MessageResponse(BaseModel):
    id: str
    conversation_id: str
    sender_id: str
    content: str
    created_at: datetime
