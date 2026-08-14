from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import get_current_user
from app.schemas.auth import TokenResponse, UserLogin, UserPublic
from app.schemas.user import UserCreate
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register_user(payload: UserCreate):
    try:
        return AuthService.create_user(payload)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Unable to register user at this time.")


@router.post("/login", response_model=TokenResponse)
def login_user(payload: UserLogin):
    try:
        return AuthService.login_user(payload.email, payload.password)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Unable to login at this time.")


@router.get("/me", response_model=UserPublic)
def get_me(current_user: dict = Depends(get_current_user)):
    return current_user
