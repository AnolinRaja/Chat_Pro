from datetime import datetime

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


class OtpRequiredResponse(BaseModel):
    requires_otp: bool = True
    email: EmailStr
    purpose: str
    message: str


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
