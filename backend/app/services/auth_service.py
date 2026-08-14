from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError, PyMongoError

from app.db import db
from app.schemas.user import UserCreate


class AuthService:
    @staticmethod
    def normalize_email(email: str) -> str:
        return email.strip().lower()

    @staticmethod
    def hash_password(password: str) -> str:
        from bcrypt import hashpw, gensalt

        return hashpw(password.encode("utf-8"), gensalt()).decode("utf-8")

    @staticmethod
    def create_user(payload: UserCreate) -> dict[str, Any]:
        collection = db.get_db()["users"]

        now = datetime.now(timezone.utc)
        doc = {
            "name": payload.name.strip(),
            "email": AuthService.normalize_email(payload.email),
            "password_hash": AuthService.hash_password(payload.password),
            "created_at": now,
            "updated_at": now,
        }

        try:
            result = collection.insert_one(doc)
        except DuplicateKeyError:
            raise HTTPException(status_code=409, detail="Email already registered.")
        except PyMongoError:
            raise HTTPException(status_code=500, detail="Unable to register user at this time.")

        created_user = collection.find_one({"_id": result.inserted_id})
        if created_user is None:
            raise HTTPException(status_code=500, detail="Unable to register user at this time.")

        return {
            "id": str(created_user["_id"]),
            "name": created_user["name"],
            "email": created_user["email"],
            "created_at": created_user["created_at"],
        }
