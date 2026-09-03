import logging

from bson import ObjectId
from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status

from app.config import settings
from app.db import db
from app.dependencies import get_current_user
from app.schemas.auth import (
    EmailRequest,
    LoginResponse,
    OtpRequiredResponse,
    OtpVerificationRequest,
    PasswordResetChallengeResponse,
    PasswordResetComplete,
    PasswordResetRequest,
    RegistrationResponse,
    TokenResponse,
    TwoFactorConfirmRequest,
    TwoFactorDisableRequest,
    TwoFactorLoginRequest,
    TwoFactorSetupResponse,
    TwoFactorStatusResponse,
    UserLogin,
    UserPublic,
)
from app.schemas.user import UserCreate
from app.services.auth_service import AuthService
from app.services.jwt_service import JWTService
from app.services.rate_limiter import auth_rate_limiter
from app.services.session_service import SessionService
from app.services.two_factor_service import TwoFactorService

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)


def _enforce_auth_rate_limit(request: Request, endpoint: str) -> None:
    client_host = request.client.host if request.client else "unknown"
    retry_after = auth_rate_limiter.check(
        f"{endpoint}:{client_host}",
        settings.AUTH_RATE_LIMIT_REQUESTS,
        settings.AUTH_RATE_LIMIT_WINDOW_SECONDS,
    )
    if retry_after is not None:
        logger.warning(
            "Authentication rate limit exceeded endpoint=%s client_ip=%s retry_after_seconds=%s",
            endpoint,
            client_host,
            retry_after,
        )
        raise HTTPException(
            status_code=429,
            detail="Too many authentication requests. Try again later.",
            headers={"Retry-After": str(retry_after)},
        )


@router.post("/register", response_model=RegistrationResponse, status_code=status.HTTP_201_CREATED)
def register_user(request: Request, payload: UserCreate):
    _enforce_auth_rate_limit(request, "register")
    try:
        return AuthService.register_user(payload)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Unable to register user at this time.")


@router.post("/login", response_model=LoginResponse)
def login_user(request: Request, response: Response, payload: UserLogin):
    _enforce_auth_rate_limit(request, "login")
    result = AuthService.login_user(payload.email, payload.password)

    # 1. Email verification required
    if result.get("requires_otp"):
        return result

    # 2. 2SV required
    if result.get("requires_2sv"):
        return result

    # 3. Direct login (2SV OFF)
    user = result["user"]
    session_id, raw_token = SessionService.create_session(str(user["_id"]))

    cookie_value = f"{session_id}.{raw_token}"
    response.set_cookie(
        key="refresh_token",
        value=cookie_value,
        httponly=settings.SESSION_COOKIE_HTTPONLY,
        secure=settings.SESSION_COOKIE_SECURE,
        samesite=settings.SESSION_COOKIE_SAMESITE,
        max_age=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600,
        path="/",
    )

    access_token = JWTService.create_access_token(str(user["_id"]))
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "requires_2sv": False,
    }


@router.post("/login/2sv", response_model=TokenResponse)
def verify_2sv_login(request: Request, response: Response, payload: TwoFactorLoginRequest):
    _enforce_auth_rate_limit(request, "login_2sv")
    user = AuthService.verify_2sv_login(payload.two_factor_token, payload.code)

    session_id, raw_token = SessionService.create_session(str(user["_id"]))

    cookie_value = f"{session_id}.{raw_token}"
    response.set_cookie(
        key="refresh_token",
        value=cookie_value,
        httponly=settings.SESSION_COOKIE_HTTPONLY,
        secure=settings.SESSION_COOKIE_SECURE,
        samesite=settings.SESSION_COOKIE_SAMESITE,
        max_age=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600,
        path="/",
    )

    access_token = JWTService.create_access_token(str(user["_id"]))
    return {
        "access_token": access_token,
        "token_type": "bearer",
    }


@router.post("/register/verify")
def verify_registration(payload: OtpVerificationRequest):
    return AuthService.verify_registration(payload.email, payload.otp)


@router.post("/register/resend")
def resend_registration(payload: EmailRequest):
    return AuthService.resend_registration(payload.email) or {"message": "Verification code sent to your email."}


@router.post("/login/verify", response_model=TokenResponse)
def verify_login(payload: OtpVerificationRequest, response: Response):
    result = AuthService.verify_login(payload.email, payload.otp)

    user = AuthService.get_user_by_email(payload.email)
    if not user:
        raise HTTPException(status_code=401, detail="Unable to complete sign in.")

    session_id, raw_token = SessionService.create_session(str(user["_id"]))

    cookie_value = f"{session_id}.{raw_token}"
    response.set_cookie(
        key="refresh_token",
        value=cookie_value,
        httponly=settings.SESSION_COOKIE_HTTPONLY,
        secure=settings.SESSION_COOKIE_SECURE,
        samesite=settings.SESSION_COOKIE_SAMESITE,
        max_age=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600,
        path="/",
    )
    return result


@router.get("/2sv/status", response_model=TwoFactorStatusResponse)
def get_2sv_status(current_user: dict = Depends(get_current_user)):
    user = db.get_db()["users"].find_one({"_id": ObjectId(current_user["id"])})
    two_factor_enabled = bool(user.get("two_factor_enabled", False)) if user else False
    recovery_hashes = user.get("two_factor_recovery_hashes", []) if user else []
    return {
        "two_factor_enabled": two_factor_enabled,
        "recovery_codes_remaining": len(recovery_hashes),
    }


@router.post("/2sv/setup", response_model=TwoFactorSetupResponse)
def setup_2sv(request: Request, current_user: dict = Depends(get_current_user)):
    _enforce_auth_rate_limit(request, "2sv_setup")
    return TwoFactorService.setup_2sv(current_user["id"], current_user["email"])


@router.post("/2sv/confirm")
def confirm_2sv(
    request: Request,
    response: Response,
    payload: TwoFactorConfirmRequest,
    current_user: dict = Depends(get_current_user)
):
    _enforce_auth_rate_limit(request, "2sv_confirm")
    result = TwoFactorService.confirm_2sv(current_user["id"], payload.code)

    # Revoke old sessions and issue a fresh session
    session_id, raw_token = SessionService.create_session(current_user["id"])
    cookie_value = f"{session_id}.{raw_token}"
    response.set_cookie(
        key="refresh_token",
        value=cookie_value,
        httponly=settings.SESSION_COOKIE_HTTPONLY,
        secure=settings.SESSION_COOKIE_SECURE,
        samesite=settings.SESSION_COOKIE_SAMESITE,
        max_age=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600,
        path="/",
        )
    return result


@router.post("/2sv/disable")
def disable_2sv(
    request: Request,
    response: Response,
    payload: TwoFactorDisableRequest,
    current_user: dict = Depends(get_current_user)
):
    _enforce_auth_rate_limit(request, "2sv_disable")
    user = db.get_db()["users"].find_one({"_id": ObjectId(current_user["id"])})
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    password_verified = AuthService.verify_password(payload.password, user.get("password_hash", ""))
    result = TwoFactorService.disable_2sv(current_user["id"], password_verified, payload.code)

    # Revoke old sessions and issue a fresh session
    session_id, raw_token = SessionService.create_session(current_user["id"])
    cookie_value = f"{session_id}.{raw_token}"
    response.set_cookie(
        key="refresh_token",
        value=cookie_value,
        httponly=settings.SESSION_COOKIE_HTTPONLY,
        secure=settings.SESSION_COOKIE_SECURE,
        samesite=settings.SESSION_COOKIE_SAMESITE,
        max_age=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600,
        path="/",
    )
    return result


@router.post("/refresh", response_model=TokenResponse)
def refresh_session(response: Response, refresh_token: str | None = Cookie(None)):
    if not refresh_token or "." not in refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session."
        )

    try:
        session_id, raw_token = refresh_token.split(".", 1)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session."
        )

    try:
        new_session_id, new_raw_token, user_id = SessionService.rotate_refresh_token(session_id, raw_token)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error during session refresh: %s", e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session."
        )

    cookie_value = f"{new_session_id}.{new_raw_token}"
    response.set_cookie(
        key="refresh_token",
        value=cookie_value,
        httponly=settings.SESSION_COOKIE_HTTPONLY,
        secure=settings.SESSION_COOKIE_SECURE,
        samesite=settings.SESSION_COOKIE_SAMESITE,
        max_age=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600,
        path="/",
    )

    access_token = JWTService.create_access_token(user_id)

    return {
        "access_token": access_token,
        "token_type": "bearer",
    }


@router.post("/logout")
def logout_user(response: Response, refresh_token: str | None = Cookie(None)):
    response.delete_cookie(
        key="refresh_token",
        path="/",
        secure=settings.SESSION_COOKIE_SECURE,
        samesite=settings.SESSION_COOKIE_SAMESITE,
    )

    if refresh_token and "." in refresh_token:
        try:
            session_id, _ = refresh_token.split(".", 1)
            SessionService.revoke_session(session_id)
        except Exception:
            pass

    return {"message": "Logged out successfully."}


@router.post("/login/resend")
def resend_login(payload: EmailRequest):
    return AuthService.resend_login(payload.email) or {"message": "Verification code sent to your email."}


@router.post("/forgot-password/request")
def request_password_reset(payload: PasswordResetRequest):
    AuthService.request_password_reset(payload.email)
    return {"message": "If an account exists for this email, a verification code has been sent."}


@router.post("/forgot-password/verify", response_model=PasswordResetChallengeResponse)
def verify_password_reset(payload: OtpVerificationRequest):
    return {
        "reset_token": AuthService.verify_password_reset(payload.email, payload.otp),
        "message": "Verification successful. You may now reset your password.",
    }


@router.post("/forgot-password/reset")
def complete_password_reset(payload: PasswordResetComplete):
    AuthService.complete_password_reset(payload.reset_token, payload.new_password)
    return {"message": "Password reset successfully."}


@router.get("/me", response_model=UserPublic)
def get_me(current_user: dict = Depends(get_current_user)):
    return current_user
