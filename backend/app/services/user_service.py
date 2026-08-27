from __future__ import annotations

import re
from typing import Any

from bson import ObjectId

from app.db import db


class UserService:
    MAX_SEARCH_RESULTS = 20

    @staticmethod
    def search_users(query: str, current_user_id: str) -> list[dict[str, str]]:
        search_text = query.strip()
        escaped_query = re.escape(search_text)
        current_user_oid = ObjectId(current_user_id)
        users = db.get_db()["users"].find(
            {
                "_id": {"$ne": current_user_oid},
                "$or": [
                    {"name": {"$regex": escaped_query, "$options": "i"}},
                    {"email": {"$regex": escaped_query, "$options": "i"}},
                ],
            },
            {"name": 1, "email": 1},
        ).sort("name", 1).limit(UserService.MAX_SEARCH_RESULTS)

        return [UserService._format_search_result(user) for user in users]

    @staticmethod
    def _format_search_result(user: dict[str, Any]) -> dict[str, str]:
        return {
            "id": str(user["_id"]),
            "name": user["name"],
            "email": user["email"],
        }