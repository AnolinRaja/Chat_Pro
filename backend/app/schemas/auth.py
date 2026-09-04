from __future__ import annotations

from datetime import datetime
from typing import Union

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class UserLogin(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(..., min_length=1)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserPublic | None = None


class LoginSuccessResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    requires_2sv: bool = False


class TwoFactorChallengeResponse(BaseModel):
    requires_2sv: bool = True
    two_factor_token: str
    message: str = "Two-Step Verification required."


class OtpRequiredResponse(BaseModel):
    requires_otp: bool = True
    email: EmailStr
    purpose: str
    message: str


LoginResponse = Union[LoginSuccessResponse, TwoFactorChallengeResponse, OtpRequiredResponse]


class RegistrationResponse(BaseModel):
    id: str
    name: str
    email: EmailStr
    created_at: datetime
    email_verified: bool
    requires_otp: bool
    verification_required: bool = True
    message: str


class OtpVerificationRequest(BaseModel):
    email: EmailStr
    otp: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")


class PasswordResetRequest(BaseModel):
    email: EmailStr


class EmailRequest(BaseModel):
    email: EmailStr


class PasswordResetComplete(BaseModel):
    reset_token: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8)

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if len(value.strip()) < 8:
            raise ValueError("Password must be at least 8 characters long.")
        return value


class PasswordResetChallengeResponse(BaseModel):
    reset_token: str
    message: str


class UserPublic(BaseModel):
    id: str
    name: str
    email: str
    two_factor_enabled: bool = False


class TwoFactorLoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    two_factor_token: str = Field(..., min_length=1)
    code: str = Field(..., min_length=1)


class TwoFactorSetupResponse(BaseModel):
    secret: str
    otpauth_uri: str
    recovery_codes: list[str]


class TwoFactorConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(..., min_length=1)


class TwoFactorDisableRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    password: str = Field(..., min_length=1)
    code: str = Field(..., min_length=1)


class TwoFactorStatusResponse(BaseModel):
    two_factor_enabled: bool
    recovery_codes_remaining: int
