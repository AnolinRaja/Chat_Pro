from fastapi import APIRouter, HTTPException, status

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
