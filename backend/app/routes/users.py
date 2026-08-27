from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.dependencies import get_current_user
from app.schemas.user_search import UserSearchResponse
from app.services.user_service import UserService

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/search", response_model=UserSearchResponse)
def search_users(
    q: str = Query(..., min_length=1, max_length=100),
    current_user: dict = Depends(get_current_user),
):
    if not q.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Search query cannot be empty.",
        )

    return {"users": UserService.search_users(q, current_user["id"])}