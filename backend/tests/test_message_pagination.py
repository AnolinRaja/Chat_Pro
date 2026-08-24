from datetime import datetime, timedelta, timezone

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient

from app.db import db
from app.main import app
from app.services.jwt_service import JWTService
from app.services.message_service import MessageService

client = TestClient(app)


@pytest.fixture
def pagination_context():
    owner_id = ObjectId()
    other_id = ObjectId()
    outsider_id = ObjectId()
    conversation_id = ObjectId()
    base_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
    conversations = db.get_db()["conversations"]
    messages = db.get_db()["messages"]
    users = db.get_db()["users"]

    users.insert_many([
        {"_id": owner_id, "name": "Pagination Owner", "email": f"{owner_id}@example.com", "password_hash": "unused"},
        {"_id": other_id, "name": "Pagination Other", "email": f"{other_id}@example.com", "password_hash": "unused"},
        {"_id": outsider_id, "name": "Pagination Outsider", "email": f"{outsider_id}@example.com", "password_hash": "unused"},
    ])
    conversations.insert_one({
        "_id": conversation_id,
        "participants": [owner_id, other_id],
        "participant_key": f"{owner_id}:{other_id}",
        "created_at": base_time,
        "updated_at": base_time,
    })

    context = {
        "owner_id": str(owner_id),
        "other_id": str(other_id),
        "outsider_id": str(outsider_id),
        "conversation_id": str(conversation_id),
        "base_time": base_time,
    }
    yield context
    messages.delete_many({"conversation_id": conversation_id})
    conversations.delete_one({"_id": conversation_id})
    users.delete_many({"_id": {"$in": [owner_id, other_id, outsider_id]}})


def add_messages(context, count, *, timestamp=None):
    conversation_id = ObjectId(context["conversation_id"])
    base_time = timestamp or context["base_time"]
    documents = [
        {
            "_id": ObjectId(),
            "conversation_id": conversation_id,
            "sender_id": ObjectId(context["owner_id"]),
            "content": f"Message {index}",
            "created_at": base_time if timestamp is not None else base_time + timedelta(seconds=index),
        }
        for index in range(count)
    ]
    db.get_db()["messages"].insert_many(documents)
    return documents


def test_default_limit_returns_50_messages(pagination_context):
    documents = add_messages(pagination_context, 55)

    result = MessageService.get_messages(
        pagination_context["conversation_id"],
        pagination_context["owner_id"],
    )

    assert len(result) == 50
    assert result[0]["id"] == str(documents[0]["_id"])
    assert result[-1]["id"] == str(documents[49]["_id"])


def test_custom_limit_and_maximum_limit_are_supported(pagination_context):
    add_messages(pagination_context, 100)

    custom = MessageService.get_messages(
        pagination_context["conversation_id"],
        pagination_context["owner_id"],
        limit=7,
    )
    maximum = MessageService.get_messages(
        pagination_context["conversation_id"],
        pagination_context["owner_id"],
        limit=100,
    )

    assert len(custom) == 7
    assert len(maximum) == 100


@pytest.mark.parametrize("limit", [0, -1, 101])
def test_invalid_limits_are_rejected(pagination_context, limit):
    with pytest.raises(Exception) as error:
        MessageService.get_messages(
            pagination_context["conversation_id"],
            pagination_context["owner_id"],
            limit=limit,
        )

    assert getattr(error.value, "status_code", None) == 400


def test_first_page_is_chronological(pagination_context):
    documents = add_messages(pagination_context, 5)

    result = MessageService.get_messages(
        pagination_context["conversation_id"],
        pagination_context["owner_id"],
        limit=5,
    )

    assert [item["id"] for item in result] == [str(document["_id"]) for document in documents]


def test_cursor_returns_next_page_without_duplicates_or_skips(pagination_context):
    add_messages(pagination_context, 6)

    first_page, cursor = MessageService.get_messages_page(
        pagination_context["conversation_id"],
        pagination_context["owner_id"],
        limit=2,
    )
    second_page, next_cursor = MessageService.get_messages_page(
        pagination_context["conversation_id"],
        pagination_context["owner_id"],
        limit=2,
        cursor=cursor,
    )
    third_page, _ = MessageService.get_messages_page(
        pagination_context["conversation_id"],
        pagination_context["owner_id"],
        limit=2,
        cursor=next_cursor,
    )

    ids = [item["id"] for item in first_page + second_page + third_page]
    assert ids == [str(document["_id"]) for document in add_messages_from_db(pagination_context)]
    assert len(ids) == len(set(ids))


def add_messages_from_db(context):
    return list(
        db.get_db()["messages"].find(
            {"conversation_id": ObjectId(context["conversation_id"])}
        ).sort([("created_at", 1), ("_id", 1)])
    )


def test_equal_timestamps_use_id_tie_breaking(pagination_context):
    documents = add_messages(
        pagination_context,
        4,
        timestamp=datetime(2026, 2, 1, tzinfo=timezone.utc),
    )
    documents.sort(key=lambda document: document["_id"])

    first_page, cursor = MessageService.get_messages_page(
        pagination_context["conversation_id"],
        pagination_context["owner_id"],
        limit=2,
    )
    second_page, _ = MessageService.get_messages_page(
        pagination_context["conversation_id"],
        pagination_context["owner_id"],
        limit=2,
        cursor=cursor,
    )

    assert [item["id"] for item in first_page + second_page] == [str(document["_id"]) for document in documents]


def test_empty_page_returns_empty_list(pagination_context):
    result = MessageService.get_messages(
        pagination_context["conversation_id"],
        pagination_context["owner_id"],
        limit=50,
    )

    assert result == []


def test_invalid_cursor_is_rejected(pagination_context):
    with pytest.raises(Exception) as error:
        MessageService.get_messages(
            pagination_context["conversation_id"],
            pagination_context["owner_id"],
            cursor="invalid-cursor",
        )

    assert getattr(error.value, "status_code", None) == 400


def test_authorization_remains_enforced_for_paginated_messages(pagination_context):
    add_messages(pagination_context, 2)

    with pytest.raises(Exception) as error:
        MessageService.get_messages(
            pagination_context["conversation_id"],
            pagination_context["outsider_id"],
            limit=1,
        )

    assert getattr(error.value, "status_code", None) == 403


def test_api_preserves_message_fields_and_exposes_cursor_header(pagination_context):
    token = JWTService.create_access_token(pagination_context["owner_id"])
    add_messages(pagination_context, 3)

    response = client.get(
        f"/conversations/{pagination_context['conversation_id']}/messages?limit=2",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert len(response.json()) == 2
    assert set(response.json()[0]) == {"id", "conversation_id", "sender_id", "content", "created_at"}
    assert response.headers.get("x-next-cursor")
