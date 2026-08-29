from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient
from pymongo.errors import DuplicateKeyError

from app.db import db
from app.config import settings
from app.main import app
from app.services.conversation_service import ConversationService

client = TestClient(app)

TEST_USERS = [
    {"name": "Unique User One", "email": "unique_user1@example.com", "password": "Password123"},
    {"name": "Unique User Two", "email": "unique_user2@example.com", "password": "Password123"},
    {"name": "Unique User Three", "email": "unique_user3@example.com", "password": "Password123"},
]


@pytest.fixture(autouse=True)
def cleanup_test_data():
    user_collection = db.get_db()["users"]
    user_collection.delete_many({"email": {"$in": [user["email"] for user in TEST_USERS]}})
    db.get_db()["conversations"].delete_many({})
    yield
    user_collection.delete_many({"email": {"$in": [user["email"] for user in TEST_USERS]}})
    db.get_db()["conversations"].delete_many({})


def register_and_login(user):
    client.post("/auth/register", json=user)
    client.post("/auth/register/verify", json={"email": user["email"], "otp": "123456"})
    response = client.post(
        "/auth/login",
        json={"email": user["email"], "password": user["password"]},
    )
    return client.post("/auth/login/verify", json={"email": user["email"], "otp": "123456"}).json()["access_token"]


def test_canonical_participant_key_is_deterministic():
    first = str(ObjectId())
    second = str(ObjectId())

    assert ConversationService.canonical_participant_key(first, second) == ":".join(sorted((first, second)))


def test_reverse_participant_order_produces_same_key():
    first = str(ObjectId())
    second = str(ObjectId())

    assert ConversationService.canonical_participant_key(first, second) == ConversationService.canonical_participant_key(second, first)


def test_normal_creation_stores_canonical_key():
    token = register_and_login(TEST_USERS[0])
    register_and_login(TEST_USERS[1])
    other_user = db.get_db()["users"].find_one({"email": TEST_USERS[1]["email"]})

    response = client.post(
        "/conversations",
        json={"other_user_id": str(other_user["_id"])},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 201
    conversation = db.get_db()["conversations"].find_one({"_id": ObjectId(response.json()["id"])})
    participants = [str(participant) for participant in conversation["participants"]]
    assert conversation["participant_key"] == ":".join(sorted(participants))


def test_sequential_duplicate_creation_returns_existing_conversation():
    token = register_and_login(TEST_USERS[0])
    register_and_login(TEST_USERS[1])
    other_user = db.get_db()["users"].find_one({"email": TEST_USERS[1]["email"]})
    payload = {"other_user_id": str(other_user["_id"])}
    headers = {"Authorization": f"Bearer {token}"}

    first = client.post("/conversations", json=payload, headers=headers)
    second = client.post("/conversations", json=payload, headers=headers)

    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json()["id"] == first.json()["id"]
    assert db.get_db()["conversations"].count_documents({}) == 1


def test_reverse_order_duplicate_creation_returns_existing_conversation():
    first_token = register_and_login(TEST_USERS[0])
    second_token = register_and_login(TEST_USERS[1])
    first_user = db.get_db()["users"].find_one({"email": TEST_USERS[0]["email"]})
    second_user = db.get_db()["users"].find_one({"email": TEST_USERS[1]["email"]})

    first = client.post(
        "/conversations",
        json={"other_user_id": str(second_user["_id"])},
        headers={"Authorization": f"Bearer {first_token}"},
    )
    second = client.post(
        "/conversations",
        json={"other_user_id": str(first_user["_id"])},
        headers={"Authorization": f"Bearer {second_token}"},
    )

    assert first.json()["id"] == second.json()["id"]
    assert db.get_db()["conversations"].count_documents({}) == 1


def test_duplicate_key_race_returns_existing_conversation(monkeypatch):
    user_id = str(ObjectId())
    other_user_id = str(ObjectId())
    participant_key = ConversationService.canonical_participant_key(user_id, other_user_id)
    existing = {
        "_id": ObjectId(),
        "participants": [ObjectId(user_id), ObjectId(other_user_id)],
        "participant_key": participant_key,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    conversations = Mock()
    conversations.find_one.side_effect = [None, None, existing]
    conversations.insert_one.side_effect = DuplicateKeyError("participant key already exists")
    users = Mock()
    users.find_one.return_value = {"_id": ObjectId(other_user_id)}

    monkeypatch.setattr(ConversationService, "_format_conversation", ConversationService._format_conversation)
    monkeypatch.setattr("app.services.conversation_service.db.get_db", lambda: {"users": users, "conversations": conversations})

    result = ConversationService.create_conversation(user_id, other_user_id)

    assert result["id"] == str(existing["_id"])
    assert conversations.insert_one.call_count == 1


def test_different_user_pairs_create_separate_conversations():
    first_token = register_and_login(TEST_USERS[0])
    register_and_login(TEST_USERS[1])
    register_and_login(TEST_USERS[2])
    second_user = db.get_db()["users"].find_one({"email": TEST_USERS[1]["email"]})
    third_user = db.get_db()["users"].find_one({"email": TEST_USERS[2]["email"]})

    first = client.post(
        "/conversations",
        json={"other_user_id": str(second_user["_id"])},
        headers={"Authorization": f"Bearer {first_token}"},
    )
    second = client.post(
        "/conversations",
        json={"other_user_id": str(third_user["_id"])},
        headers={"Authorization": f"Bearer {first_token}"},
    )

    assert first.json()["id"] != second.json()["id"]
    assert db.get_db()["conversations"].count_documents({}) == 2


def test_response_shape_remains_unchanged():
    token = register_and_login(TEST_USERS[0])
    register_and_login(TEST_USERS[1])
    other_user = db.get_db()["users"].find_one({"email": TEST_USERS[1]["email"]})

    response = client.post(
        "/conversations",
        json={"other_user_id": str(other_user["_id"])},
        headers={"Authorization": f"Bearer {token}"},
    )

    body = response.json()
    assert set(body) == {"id", "participants", "other_user", "created_at", "updated_at"}
    assert body["other_user"] == {
        "id": str(other_user["_id"]),
        "name": TEST_USERS[1]["name"],
        "email": TEST_USERS[1]["email"],
    }


def test_conversation_and_messages_are_available_after_fresh_login():
    token1 = register_and_login(TEST_USERS[0])
    register_and_login(TEST_USERS[1])
    other_user = db.get_db()["users"].find_one({"email": TEST_USERS[1]["email"]})

    created = client.post(
        "/conversations",
        json={"other_user_id": str(other_user["_id"])},
        headers={"Authorization": f"Bearer {token1}"},
    )
    conversation_id = created.json()["id"]
    sent = client.post(
        f"/conversations/{conversation_id}/messages",
        json={"content": "Persisted message"},
        headers={"Authorization": f"Bearer {token1}"},
    )
    assert sent.status_code == 201

    with patch.object(settings, "OTP_RESEND_COOLDOWN_SECONDS", 0):
        client.post(
            "/auth/login",
            json={"email": TEST_USERS[0]["email"], "password": TEST_USERS[0]["password"]},
        )
        fresh_token = client.post(
            "/auth/login/verify",
            json={"email": TEST_USERS[0]["email"], "otp": "123456"},
        ).json()["access_token"]
    conversations = client.get(
        "/conversations",
        headers={"Authorization": f"Bearer {fresh_token}"},
    )
    messages = client.get(
        f"/conversations/{conversation_id}/messages",
        headers={"Authorization": f"Bearer {fresh_token}"},
    )

    assert conversations.status_code == 200
    assert conversations.json()[0]["id"] == conversation_id
    assert conversations.json()[0]["other_user"]["name"] == TEST_USERS[1]["name"]
    assert messages.status_code == 200
    assert messages.json()[0]["content"] == "Persisted message"


def test_existing_authorization_behavior_remains_unchanged():
    owner_token = register_and_login(TEST_USERS[0])
    register_and_login(TEST_USERS[1])
    outsider_token = register_and_login(TEST_USERS[2])
    second_user = db.get_db()["users"].find_one({"email": TEST_USERS[1]["email"]})

    conversation = client.post(
        "/conversations",
        json={"other_user_id": str(second_user["_id"])},
        headers={"Authorization": f"Bearer {owner_token}"},
    ).json()

    response = client.get(
        "/conversations",
        headers={"Authorization": f"Bearer {outsider_token}"},
    )

    assert response.status_code == 200
    assert conversation["id"] not in {item["id"] for item in response.json()}


def test_unique_participant_key_index_is_sparse_and_unique():
    indexes = list(db.get_db()["conversations"].list_indexes())
    index = next(item for item in indexes if item["name"] == "unique_conversation_participant_key_idx")

    assert index["key"] == {"participant_key": 1}
    assert index["unique"] is True
    assert index["sparse"] is True
