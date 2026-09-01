from __future__ import annotations

import re
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, field_validator


class OrganizationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    org_id: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=100)
    join_code: str = Field(..., min_length=6, max_length=100)

    @field_validator("org_id")
    @classmethod
    def normalize_org_id(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError("Organization ID cannot be empty.")
        if not re.match(r"^[a-z0-9\-_]+$", normalized):
            raise ValueError("Organization ID must be alphanumeric and may only contain letters, numbers, hyphens, or underscores.")
        return normalized

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Name cannot be empty.")
        return normalized

    @field_validator("join_code")
    @classmethod
    def validate_join_code(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 6:
            raise ValueError("Join code must be at least 6 characters long.")
        return normalized


class OrganizationResponse(BaseModel):
    id: str
    org_id: str
    name: str
    is_active: bool = True
    created_at: datetime
    updated_at: datetime


class OrganizationMembershipResponse(BaseModel):
    id: str
    user_id: str
    organization_id: str
    role: str
    created_at: datetime


class OrganizationRegistrationRequestResponse(BaseModel):
    id: str
    user_id: str
    organization_id: str
    status: str
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class OrganizationJoinRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    org_id: str = Field(..., min_length=1)
    join_code: str = Field(..., min_length=1)

    @field_validator("org_id")
    @classmethod
    def normalize_org_id(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError("Organization ID cannot be empty.")
        return normalized

    @field_validator("join_code")
    @classmethod
    def validate_join_code(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Join code cannot be empty.")
        return normalized


class OrganizationMemberDetailResponse(BaseModel):
    membership_id: str
    user_id: str
    name: str
    email: str
    role: str
    created_at: datetime


class UserOrganizationMembershipStatus(BaseModel):
    id: str
    organization_id: str
    organization_name: str
    org_id: str
    role: str
    created_at: datetime


class UserOrganizationRequestStatus(BaseModel):
    id: str
    organization_id: str
    organization_name: str
    org_id: str
    status: str
    created_at: datetime
    updated_at: datetime


class UserOrganizationStatusResponse(BaseModel):
    memberships: list[UserOrganizationMembershipStatus]
    requests: list[UserOrganizationRequestStatus]
