import pytest
from bson import ObjectId
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.db import db
from app.main import app
from app.services.connection_manager import connection_manager

client = TestClient(app)

TEST_USERS = [
    {"name": "User One", "email": "ws_user1@example.com", "password": "Password123"},
    {"name": "User Two", "email": "ws_user2@example.com", "password": "Password123"},
    {"name": "User Three", "email": "ws_user3@example.com", "password": "Password123"},
]


@pytest.fixture(autouse=True)
def cleanup_test_data():
    collection = db.get_db()["users"]
    collection.delete_many({"email": {"$in": [u["email"] for u in TEST_USERS]}})
    db.get_db()["conversations"].delete_many({})
    db.get_db()["messages"].delete_many({})
    connection_manager.clear_all()
    yield
    collection.delete_many({"email": {"$in": [u["email"] for u in TEST_USERS]}})
    db.get_db()["conversations"].delete_many({})
    db.get_db()["messages"].delete_many({})
    connection_manager.clear_all()


def register_and_login(user_data):
    client.post("/auth/register", json=user_data)
    response = client.post("/auth/login", json={"email": user_data["email"], "password": user_data["password"]})
    return response.json()["access_token"]


def test_authenticated_participant_can_establish_websocket_connection():
    token1 = register_and_login(TEST_USERS[0])
    token2 = register_and_login(TEST_USERS[1])
    user2 = db.get_db()["users"].find_one({"email": TEST_USERS[1]["email"]})

    response = client.post(
        "/conversations",
        json={"other_user_id": str(user2["_id"])},
        headers={"Authorization": f"Bearer {token1}"},
    )
    conv_id = response.json()["id"]

    with client.websocket_connect(f"/ws/conversations/{conv_id}?token={token2}") as websocket:
        assert websocket is not None


def test_both_participants_can_establish_connections():
    token1 = register_and_login(TEST_USERS[0])
    token2 = register_and_login(TEST_USERS[1])
    user2 = db.get_db()["users"].find_one({"email": TEST_USERS[1]["email"]})

    response = client.post(
        "/conversations",
        json={"other_user_id": str(user2["_id"])},
        headers={"Authorization": f"Bearer {token1}"},
    )
    conv_id = response.json()["id"]

    with client.websocket_connect(f"/ws/conversations/{conv_id}?token={token1}") as ws_one:
        with client.websocket_connect(f"/ws/conversations/{conv_id}?token={token2}") as ws_two:
            assert ws_one is not None
            assert ws_two is not None


def test_unauthenticated_or_invalid_jwt_connection_is_rejected():
    token1 = register_and_login(TEST_USERS[0])
    token2 = register_and_login(TEST_USERS[1])
    user2 = db.get_db()["users"].find_one({"email": TEST_USERS[1]["email"]})
    response = client.post(
        "/conversations",
        json={"other_user_id": str(user2["_id"])},
        headers={"Authorization": f"Bearer {token1}"},
    )
    conv_id = response.json()["id"]

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/ws/conversations/{conv_id}?token=not-a-valid-jwt"):
            pass

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/ws/conversations/{conv_id}"):
            pass

    expired_token = token2[:10] + "bad"
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/ws/conversations/{conv_id}?token={expired_token}"):
            pass


def test_nonexistent_conversation_is_rejected():
    token = register_and_login(TEST_USERS[0])

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/ws/conversations/{str(ObjectId())}?token={token}"):
            pass


def test_non_participant_user_is_rejected():
    token1 = register_and_login(TEST_USERS[0])
    token2 = register_and_login(TEST_USERS[1])
    token3 = register_and_login(TEST_USERS[2])
    user2 = db.get_db()["users"].find_one({"email": TEST_USERS[1]["email"]})

    response = client.post(
        "/conversations",
        json={"other_user_id": str(user2["_id"])},
        headers={"Authorization": f"Bearer {token1}"},
    )
    conv_id = response.json()["id"]

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/ws/conversations/{conv_id}?token={token3}"):
            pass

    with client.websocket_connect(f"/ws/conversations/{conv_id}?token={token2}") as websocket:
        assert websocket is not None


def test_invalid_conversation_id_is_handled_safely():
    token = register_and_login(TEST_USERS[0])

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/ws/conversations/not-a-valid-id?token={token}"):
            pass


def test_disconnect_removes_the_connection_correctly():
    token1 = register_and_login(TEST_USERS[0])
    token2 = register_and_login(TEST_USERS[1])
    user2 = db.get_db()["users"].find_one({"email": TEST_USERS[1]["email"]})

    response = client.post(
        "/conversations",
        json={"other_user_id": str(user2["_id"])},
        headers={"Authorization": f"Bearer {token1}"},
    )
    conv_id = response.json()["id"]

    with client.websocket_connect(f"/ws/conversations/{conv_id}?token={token1}") as websocket:
        assert len(connection_manager.get_connections(conv_id)) == 1

    assert len(connection_manager.get_connections(conv_id)) == 0

    with client.websocket_connect(f"/ws/conversations/{conv_id}?token={token2}") as ws_two:
        assert len(connection_manager.get_connections(conv_id)) == 1

    assert len(connection_manager.get_connections(conv_id)) == 0
