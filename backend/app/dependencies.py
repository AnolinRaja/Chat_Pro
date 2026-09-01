from __future__ import annotations

from typing import Any

from bson import ObjectId
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.db import db
from app.services.jwt_service import JWTService

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user_from_token(token: str) -> dict[str, Any]:
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication credentials.")

    try:
        payload = JWTService.decode_access_token(token)
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication credentials.")

    user_id = payload.get("sub")
    if not user_id or payload.get("type") == "admin":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication credentials.")

    try:
        user = db.get_db()["users"].find_one({"_id": ObjectId(user_id)})
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication credentials.")

    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication credentials.")

    return {
        "id": str(user["_id"]),
        "name": user["name"],
        "email": user["email"],
    }


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict[str, Any]:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication credentials.")

    return await get_current_user_from_token(credentials.credentials)


async def get_current_admin(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict[str, Any]:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication credentials.")

    token = credentials.credentials
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication credentials.")

    try:
        payload = JWTService.decode_access_token(token)
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication credentials.")

    if payload.get("type") != "admin":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication credentials.")

    admin_id = payload.get("sub")
    if not admin_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication credentials.")

    try:
        admin_oid = ObjectId(admin_id)
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication credentials.")

    try:
        admin = db.get_db()["admin_users"].find_one({"_id": admin_oid})
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication credentials.")

    if admin is None or not admin.get("is_active"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication credentials.")

    return {
        "id": str(admin["_id"]),
        "name": admin["name"],
        "email": admin["email"],
        "role": admin["role"],
        "organization_id": str(admin["organization_id"]) if admin.get("organization_id") else None,
        "is_active": admin.get("is_active", True),
    }


def require_system_admin(
    current_admin: dict[str, Any] = Depends(get_current_admin),
) -> dict[str, Any]:
    if current_admin.get("role") != "system_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="System administrator access required."
        )
    return current_admin


def require_org_admin(
    current_admin: dict[str, Any] = Depends(get_current_admin),
) -> dict[str, Any]:
    if current_admin.get("role") not in {"system_admin", "org_admin"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator access required."
        )
    return current_admin


def assert_admin_organization_access(
    admin: dict[str, Any],
    target_org_id: str | ObjectId,
) -> None:
    if admin.get("role") == "system_admin":
        return

    admin_org_id = str(admin.get("organization_id"))
    target_str_id = str(target_org_id)
    if admin_org_id != target_str_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied for this organization."
        )
