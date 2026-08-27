from datetime import datetime

from pydantic import BaseModel, Field


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
