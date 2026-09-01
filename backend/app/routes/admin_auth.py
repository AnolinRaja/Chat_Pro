from __future__ import annotations

import logging
from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status

from app.config import settings
from app.dependencies import get_current_admin
from app.schemas.admin import AdminLogin, AdminResponse, AdminTokenResponse
from app.services.admin_auth_service import AdminAuthService
from app.services.admin_session_service import AdminSessionService
from app.services.jwt_service import JWTService
from app.services.rate_limiter import auth_rate_limiter

router = APIRouter(prefix="/admin/auth", tags=["admin-auth"])
logger = logging.getLogger(__name__)


def _enforce_admin_auth_rate_limit(request: Request, endpoint: str) -> None:
    client_host = request.client.host if request.client else "unknown"
    retry_after = auth_rate_limiter.check(
        f"{endpoint}:{client_host}",
        settings.AUTH_RATE_LIMIT_REQUESTS,
        settings.AUTH_RATE_LIMIT_WINDOW_SECONDS,
    )
    if retry_after is not None:
        logger.warning(
            "Admin authentication rate limit exceeded endpoint=%s client_ip=%s retry_after_seconds=%s",
            endpoint,
            client_host,
            retry_after,
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many authentication requests. Try again later.",
            headers={"Retry-After": str(retry_after)},
        )


@router.post("/login", response_model=AdminTokenResponse)
def login_admin(request: Request, payload: AdminLogin, response: Response):
    _enforce_admin_auth_rate_limit(request, "admin_login")

    admin = AdminAuthService.authenticate_admin(payload.email, payload.password)

    session_id, raw_token = AdminSessionService.create_session(admin["id"])

    cookie_value = f"{session_id}.{raw_token}"
    response.set_cookie(
        key="admin_refresh_token",
        value=cookie_value,
        httponly=settings.SESSION_COOKIE_HTTPONLY,
        secure=settings.SESSION_COOKIE_SECURE,
        samesite=settings.SESSION_COOKIE_SAMESITE,
        max_age=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600,
        path="/admin",
    )

    access_token = JWTService.create_admin_access_token(
        admin_id=admin["id"],
        role=admin["role"],
        organization_id=admin.get("organization_id"),
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "admin": AdminResponse(**admin),
    }


@router.post("/refresh")
def refresh_admin_session(response: Response, admin_refresh_token: str | None = Cookie(None)):
    if not admin_refresh_token or "." not in admin_refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session."
        )

    try:
        session_id, raw_token = admin_refresh_token.split(".", 1)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session."
        )

    try:
        new_session_id, new_raw_token, admin_id = AdminSessionService.rotate_refresh_token(session_id, raw_token)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error during admin session refresh: %s", e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session."
        )

    admin = AdminAuthService.get_admin_by_id(admin_id)
    if not admin:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session."
        )

    cookie_value = f"{new_session_id}.{new_raw_token}"
    response.set_cookie(
        key="admin_refresh_token",
        value=cookie_value,
        httponly=settings.SESSION_COOKIE_HTTPONLY,
        secure=settings.SESSION_COOKIE_SECURE,
        samesite=settings.SESSION_COOKIE_SAMESITE,
        max_age=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600,
        path="/admin",
    )

    access_token = JWTService.create_admin_access_token(
        admin_id=admin["id"],
        role=admin["role"],
        organization_id=admin.get("organization_id"),
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
    }


@router.post("/logout")
def logout_admin(response: Response, admin_refresh_token: str | None = Cookie(None)):
    response.delete_cookie(
        key="admin_refresh_token",
        path="/admin",
        secure=settings.SESSION_COOKIE_SECURE,
        samesite=settings.SESSION_COOKIE_SAMESITE,
    )

    if admin_refresh_token and "." in admin_refresh_token:
        try:
            session_id, _ = admin_refresh_token.split(".", 1)
            AdminSessionService.revoke_session(session_id)
        except Exception:
            pass

    return {"message": "Admin logged out successfully."}


@router.get("/me", response_model=AdminResponse)
def get_admin_me(current_admin: dict = Depends(get_current_admin)):
    return current_admin
