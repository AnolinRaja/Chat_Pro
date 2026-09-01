from __future__ import annotations

from datetime import datetime
from typing import Literal
from bson import ObjectId
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator


class AdminLogin(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(..., min_length=1)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class AdminCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    name: str = Field(..., min_length=1)
    password: str = Field(..., min_length=8)
    role: Literal["system_admin", "org_admin"]
    organization_id: str | None = None

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Name cannot be empty.")
        return normalized

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if len(value.strip()) < 8:
            raise ValueError("Password must be at least 8 characters long.")
        return value

    @model_validator(mode="after")
    def validate_role_organization(self) -> AdminCreate:
        if self.role == "system_admin":
            if self.organization_id is not None:
                raise ValueError("System administrator must not be associated with an organization.")
        elif self.role == "org_admin":
            if not self.organization_id:
                raise ValueError("Organization administrator must be associated with an organization.")
            if not ObjectId.is_valid(self.organization_id):
                raise ValueError("organization_id must be a valid ObjectId.")
        return self


class AdminResponse(BaseModel):
    id: str
    email: str
    name: str
    role: str
    organization_id: str | None = None
    is_active: bool = True
    created_at: datetime


class AdminTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    admin: AdminResponse
