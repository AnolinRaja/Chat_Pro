import pytest
from fastapi.testclient import TestClient
from bson import ObjectId

from app.db import db
from app.main import app

client = TestClient(app)

TEST_USERS = [
    {"name": "User One", "email": "user1@example.com", "password": "Password123"},
    {"name": "User Two", "email": "user2@example.com", "password": "Password123"},
]


@pytest.fixture(autouse=True)
def cleanup_test_data():
    collection = db.get_db()["users"]
    collection.delete_many({"email": {"$in": [u["email"] for u in TEST_USERS]}})
    db.get_db()["conversations"].delete_many({})
    db.get_db()["messages"].delete_many({})
    yield
    collection.delete_many({"email": {"$in": [u["email"] for u in TEST_USERS]}})
    db.get_db()["conversations"].delete_many({})
    db.get_db()["messages"].delete_many({})


def register_and_login(user_data):
    client.post("/auth/register", json=user_data)
    client.post("/auth/register/verify", json={"email": user_data["email"], "otp": "123456"})
    response = client.post("/auth/login", json={"email": user_data["email"], "password": user_data["password"]})
    return response.json()["access_token"]


def test_authenticated_user_can_send_message():
    token1 = register_and_login(TEST_USERS[0])
    register_and_login(TEST_USERS[1])
    user2 = db.get_db()["users"].find_one({"email": TEST_USERS[1]["email"]})

    conv_response = client.post(
        "/conversations",
        json={"other_user_id": str(user2["_id"])},
        headers={"Authorization": f"Bearer {token1}"},
    )
    conv_id = conv_response.json()["id"]

    response = client.post(
        f"/conversations/{conv_id}/messages",
        json={"content": "Hello!"},
        headers={"Authorization": f"Bearer {token1}"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["content"] == "Hello!"
    assert "sender_id" in body
    assert body["conversation_id"] == conv_id


def test_empty_message_rejected():
    token1 = register_and_login(TEST_USERS[0])
    register_and_login(TEST_USERS[1])
    user2 = db.get_db()["users"].find_one({"email": TEST_USERS[1]["email"]})

    conv_response = client.post(
        "/conversations",
        json={"other_user_id": str(user2["_id"])},
        headers={"Authorization": f"Bearer {token1}"},
    )
    conv_id = conv_response.json()["id"]

    response = client.post(
        f"/conversations/{conv_id}/messages",
        json={"content": ""},
        headers={"Authorization": f"Bearer {token1}"},
    )

    assert response.status_code == 422 or response.status_code == 400


def test_whitespace_only_message_rejected():
    token1 = register_and_login(TEST_USERS[0])
    register_and_login(TEST_USERS[1])
    user2 = db.get_db()["users"].find_one({"email": TEST_USERS[1]["email"]})

    conv_response = client.post(
        "/conversations",
        json={"other_user_id": str(user2["_id"])},
        headers={"Authorization": f"Bearer {token1}"},
    )
    conv_id = conv_response.json()["id"]

    response = client.post(
        f"/conversations/{conv_id}/messages",
        json={"content": "   "},
        headers={"Authorization": f"Bearer {token1}"},
    )

    assert response.status_code == 422 or response.status_code == 400


def test_message_content_trimmed():
    token1 = register_and_login(TEST_USERS[0])
    register_and_login(TEST_USERS[1])
    user2 = db.get_db()["users"].find_one({"email": TEST_USERS[1]["email"]})

    conv_response = client.post(
        "/conversations",
        json={"other_user_id": str(user2["_id"])},
        headers={"Authorization": f"Bearer {token1}"},
    )
    conv_id = conv_response.json()["id"]

    response = client.post(
        f"/conversations/{conv_id}/messages",
        json={"content": "  Hello World  "},
        headers={"Authorization": f"Bearer {token1}"},
    )

    assert response.status_code == 201
    assert response.json()["content"] == "Hello World"


def test_message_too_long_rejected():
    token1 = register_and_login(TEST_USERS[0])
    register_and_login(TEST_USERS[1])
    user2 = db.get_db()["users"].find_one({"email": TEST_USERS[1]["email"]})

    conv_response = client.post(
        "/conversations",
        json={"other_user_id": str(user2["_id"])},
        headers={"Authorization": f"Bearer {token1}"},
    )
    conv_id = conv_response.json()["id"]

    long_content = "a" * 5001

    response = client.post(
        f"/conversations/{conv_id}/messages",
        json={"content": long_content},
        headers={"Authorization": f"Bearer {token1}"},
    )

    assert response.status_code == 400 or response.status_code == 422


def test_unauthenticated_user_cannot_send_message():
    token1 = register_and_login(TEST_USERS[0])
    register_and_login(TEST_USERS[1])
    user2 = db.get_db()["users"].find_one({"email": TEST_USERS[1]["email"]})

    conv_response = client.post(
        "/conversations",
        json={"other_user_id": str(user2["_id"])},
        headers={"Authorization": f"Bearer {token1}"},
    )
    conv_id = conv_response.json()["id"]

    response = client.post(
        f"/conversations/{conv_id}/messages",
        json={"content": "Hello!"},
    )

    assert response.status_code == 401


def test_invalid_conversation_id_rejected():
    token1 = register_and_login(TEST_USERS[0])

    response = client.post(
        "/conversations/not-a-valid-id/messages",
        json={"content": "Hello!"},
        headers={"Authorization": f"Bearer {token1}"},
    )

    assert response.status_code == 400


def test_nonexistent_conversation_rejected():
    token1 = register_and_login(TEST_USERS[0])

    response = client.post(
        f"/conversations/{str(ObjectId())}/messages",
        json={"content": "Hello!"},
        headers={"Authorization": f"Bearer {token1}"},
    )

    assert response.status_code == 404


def test_user_cannot_message_conversation_they_are_not_part_of():
    token1 = register_and_login(TEST_USERS[0])
    token2 = register_and_login(TEST_USERS[1])
    token3 = register_and_login({"name": "User Three", "email": "user3@example.com", "password": "Password123"})
    user2 = db.get_db()["users"].find_one({"email": TEST_USERS[1]["email"]})

    conv_response = client.post(
        "/conversations",
        json={"other_user_id": str(user2["_id"])},
        headers={"Authorization": f"Bearer {token1}"},
    )
    conv_id = conv_response.json()["id"]

    response = client.post(
        f"/conversations/{conv_id}/messages",
        json={"content": "Unauthorized message"},
        headers={"Authorization": f"Bearer {token3}"},
    )

    assert response.status_code == 403


def test_authenticated_user_can_retrieve_messages():
    token1 = register_and_login(TEST_USERS[0])
    register_and_login(TEST_USERS[1])
    user2 = db.get_db()["users"].find_one({"email": TEST_USERS[1]["email"]})

    conv_response = client.post(
        "/conversations",
        json={"other_user_id": str(user2["_id"])},
        headers={"Authorization": f"Bearer {token1}"},
    )
    conv_id = conv_response.json()["id"]

    client.post(
        f"/conversations/{conv_id}/messages",
        json={"content": "Message 1"},
        headers={"Authorization": f"Bearer {token1}"},
    )
    client.post(
        f"/conversations/{conv_id}/messages",
        json={"content": "Message 2"},
        headers={"Authorization": f"Bearer {token1}"},
    )

    response = client.get(
        f"/conversations/{conv_id}/messages",
        headers={"Authorization": f"Bearer {token1}"},
    )

    assert response.status_code == 200
    messages = response.json()
    assert len(messages) == 2
    assert messages[0]["content"] == "Message 1"
    assert messages[1]["content"] == "Message 2"


def test_messages_ordered_by_creation_time():
    token1 = register_and_login(TEST_USERS[0])
    register_and_login(TEST_USERS[1])
    user2 = db.get_db()["users"].find_one({"email": TEST_USERS[1]["email"]})

    conv_response = client.post(
        "/conversations",
        json={"other_user_id": str(user2["_id"])},
        headers={"Authorization": f"Bearer {token1}"},
    )
    conv_id = conv_response.json()["id"]

    for i in range(1, 4):
        client.post(
            f"/conversations/{conv_id}/messages",
            json={"content": f"Message {i}"},
            headers={"Authorization": f"Bearer {token1}"},
        )

    response = client.get(
        f"/conversations/{conv_id}/messages",
        headers={"Authorization": f"Bearer {token1}"},
    )

    messages = response.json()
    for i in range(len(messages)):
        assert messages[i]["content"] == f"Message {i + 1}"


def test_unauthenticated_user_cannot_retrieve_messages():
    token1 = register_and_login(TEST_USERS[0])
    register_and_login(TEST_USERS[1])
    user2 = db.get_db()["users"].find_one({"email": TEST_USERS[1]["email"]})

    conv_response = client.post(
        "/conversations",
        json={"other_user_id": str(user2["_id"])},
        headers={"Authorization": f"Bearer {token1}"},
    )
    conv_id = conv_response.json()["id"]

    response = client.get(
        f"/conversations/{conv_id}/messages",
    )

    assert response.status_code == 401


def test_user_cannot_retrieve_messages_from_conversation_they_are_not_part_of():
    token1 = register_and_login(TEST_USERS[0])
    token2 = register_and_login(TEST_USERS[1])
    token3 = register_and_login({"name": "User Three", "email": "user3@example.com", "password": "Password123"})
    user2 = db.get_db()["users"].find_one({"email": TEST_USERS[1]["email"]})

    conv_response = client.post(
        "/conversations",
        json={"other_user_id": str(user2["_id"])},
        headers={"Authorization": f"Bearer {token1}"},
    )
    conv_id = conv_response.json()["id"]

    response = client.get(
        f"/conversations/{conv_id}/messages",
        headers={"Authorization": f"Bearer {token3}"},
    )

    assert response.status_code == 403
