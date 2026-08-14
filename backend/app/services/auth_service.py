from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from bcrypt import checkpw, gensalt, hashpw
from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError, PyMongoError

from app.db import db
from app.schemas.user import UserCreate
from app.services.jwt_service import JWTService


class AuthService:
    @staticmethod
    def normalize_email(email: str) -> str:
        return email.strip().lower()

    @staticmethod
    def hash_password(password: str) -> str:
        return hashpw(password.encode("utf-8"), gensalt()).decode("utf-8")

    @staticmethod
    def verify_password(password: str, password_hash: str) -> bool:
        return checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))

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

    @staticmethod
    def login_user(email: str, password: str) -> dict[str, str]:
        normalized_email = AuthService.normalize_email(email)
        user = db.get_db()["users"].find_one({"email": normalized_email})

        if user is None or not AuthService.verify_password(password, user.get("password_hash", "")):
            raise HTTPException(status_code=401, detail="Invalid email or password.")

        access_token = JWTService.create_access_token(str(user["_id"]))
        return {
            "access_token": access_token,
            "token_type": "bearer",
        }
