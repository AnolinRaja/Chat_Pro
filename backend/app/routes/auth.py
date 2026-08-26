import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.config import settings
from app.dependencies import get_current_user
from app.schemas.auth import TokenResponse, UserLogin, UserPublic
from app.schemas.user import UserCreate
from app.services.auth_service import AuthService
from app.services.rate_limiter import auth_rate_limiter

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


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register_user(request: Request, payload: UserCreate):
    _enforce_auth_rate_limit(request, "register")
    try:
        return AuthService.create_user(payload)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Unable to register user at this time.")


@router.post("/login", response_model=TokenResponse)
def login_user(request: Request, payload: UserLogin):
    _enforce_auth_rate_limit(request, "login")
    try:
        return AuthService.login_user(payload.email, payload.password)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Unable to login at this time.")


@router.get("/me", response_model=UserPublic)
def get_me(current_user: dict = Depends(get_current_user)):
    return current_user
