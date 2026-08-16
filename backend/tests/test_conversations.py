import pytest
from fastapi.testclient import TestClient
from bson import ObjectId

from app.db import db
from app.main import app

client = TestClient(app)

TEST_USERS = [
    {"name": "User One", "email": "user1@example.com", "password": "Password123"},
    {"name": "User Two", "email": "user2@example.com", "password": "Password123"},
    {"name": "User Three", "email": "user3@example.com", "password": "Password123"},
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
    response = client.post("/auth/login", json={"email": user_data["email"], "password": user_data["password"]})
    return response.json()["access_token"]


def test_authenticated_user_can_create_conversation():
    token1 = register_and_login(TEST_USERS[0])
    token2 = register_and_login(TEST_USERS[1])

    user2 = db.get_db()["users"].find_one({"email": TEST_USERS[1]["email"]})

    response = client.post(
        "/conversations",
        json={"other_user_id": str(user2["_id"])},
        headers={"Authorization": f"Bearer {token1}"},
    )

    assert response.status_code == 201
    body = response.json()
    assert "id" in body
    assert "participants" in body
    assert len(body["participants"]) == 2


def test_unauthenticated_user_cannot_create_conversation():
    register_and_login(TEST_USERS[0])
    register_and_login(TEST_USERS[1])
    user2 = db.get_db()["users"].find_one({"email": TEST_USERS[1]["email"]})

    response = client.post(
        "/conversations",
        json={"other_user_id": str(user2["_id"])},
    )

    assert response.status_code == 401


def test_invalid_other_user_id_rejected():
    token1 = register_and_login(TEST_USERS[0])

    response = client.post(
        "/conversations",
        json={"other_user_id": "not-a-valid-id"},
        headers={"Authorization": f"Bearer {token1}"},
    )

    assert response.status_code == 400


def test_nonexistent_other_user_rejected():
    token1 = register_and_login(TEST_USERS[0])

    response = client.post(
        "/conversations",
        json={"other_user_id": str(ObjectId())},
        headers={"Authorization": f"Bearer {token1}"},
    )

    assert response.status_code == 404


def test_user_cannot_create_conversation_with_themselves():
    token1 = register_and_login(TEST_USERS[0])
    user1 = db.get_db()["users"].find_one({"email": TEST_USERS[0]["email"]})

    response = client.post(
        "/conversations",
        json={"other_user_id": str(user1["_id"])},
        headers={"Authorization": f"Bearer {token1}"},
    )

    assert response.status_code == 400


def test_duplicate_conversation_does_not_create_another():
    token1 = register_and_login(TEST_USERS[0])
    register_and_login(TEST_USERS[1])
    user2 = db.get_db()["users"].find_one({"email": TEST_USERS[1]["email"]})

    response1 = client.post(
        "/conversations",
        json={"other_user_id": str(user2["_id"])},
        headers={"Authorization": f"Bearer {token1}"},
    )
    conv_id_1 = response1.json()["id"]

    response2 = client.post(
        "/conversations",
        json={"other_user_id": str(user2["_id"])},
        headers={"Authorization": f"Bearer {token1}"},
    )
    conv_id_2 = response2.json()["id"]

    assert conv_id_1 == conv_id_2


def test_user_can_list_their_conversations():
    token1 = register_and_login(TEST_USERS[0])
    register_and_login(TEST_USERS[1])
    user2 = db.get_db()["users"].find_one({"email": TEST_USERS[1]["email"]})

    client.post(
        "/conversations",
        json={"other_user_id": str(user2["_id"])},
        headers={"Authorization": f"Bearer {token1}"},
    )

    response = client.get(
        "/conversations",
        headers={"Authorization": f"Bearer {token1}"},
    )

    assert response.status_code == 200
    conversations = response.json()
    assert len(conversations) == 1


def test_user_cannot_see_another_users_conversations():
    token1 = register_and_login(TEST_USERS[0])
    token2 = register_and_login(TEST_USERS[1])
    token3 = register_and_login(TEST_USERS[2])
    user2 = db.get_db()["users"].find_one({"email": TEST_USERS[1]["email"]})
    user3 = db.get_db()["users"].find_one({"email": TEST_USERS[2]["email"]})

    client.post(
        "/conversations",
        json={"other_user_id": str(user2["_id"])},
        headers={"Authorization": f"Bearer {token1}"},
    )

    response = client.get(
        "/conversations",
        headers={"Authorization": f"Bearer {token2}"},
    )

    conversations = response.json()
    assert len(conversations) == 1

    response_user3 = client.get(
        "/conversations",
        headers={"Authorization": f"Bearer {token3}"},
    )

    conversations_user3 = response_user3.json()
    assert len(conversations_user3) == 0
