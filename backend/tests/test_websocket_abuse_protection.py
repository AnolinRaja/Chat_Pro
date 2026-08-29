import json
from datetime import datetime, timezone

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect, WebSocketState

from app.config import settings
from app.db import db
from app.main import app
from app.services.connection_manager import ConnectionManager
from app.services.rate_limiter import auth_rate_limiter

client = TestClient(app)

TEST_USERS = [
    {"name": "Abuse User One", "email": "abuse-one@example.com", "password": "Password123"},
    {"name": "Abuse User Two", "email": "abuse-two@example.com", "password": "Password123"},
]


@pytest.fixture(autouse=True)
def cleanup_test_data():
    users = db.get_db()["users"]
    users.delete_many({"email": {"$in": [user["email"] for user in TEST_USERS]}})
    db.get_db()["conversations"].delete_many({})
    db.get_db()["messages"].delete_many({})
    auth_rate_limiter.clear()
    yield
    users.delete_many({"email": {"$in": [user["email"] for user in TEST_USERS]}})
    db.get_db()["conversations"].delete_many({})
    db.get_db()["messages"].delete_many({})
    auth_rate_limiter.clear()


def register_and_login(user):
    client.post("/auth/register", json=user)
    client.post("/auth/register/verify", json={"email": user["email"], "otp": "123456"})
    client.post(
        "/auth/login",
        json={"email": user["email"], "password": user["password"]},
    )
    return client.post("/auth/login/verify", json={"email": user["email"], "otp": "123456"}).json()["access_token"]


def create_conversation():
    first_token = register_and_login(TEST_USERS[0])
    second_token = register_and_login(TEST_USERS[1])
    second_user = db.get_db()["users"].find_one({"email": TEST_USERS[1]["email"]})
    conversation_id = client.post(
        "/conversations",
        json={"other_user_id": str(second_user["_id"])},
        headers={"Authorization": f"Bearer {first_token}"},
    ).json()["id"]
    return conversation_id, first_token, second_token


def receive_message_and_broadcast(websocket):
    acknowledgement = websocket.receive_json()
    broadcast = websocket.receive_json()
    return acknowledgement, broadcast


def test_user_can_open_connections_under_and_at_limit(monkeypatch):
    conversation_id, token, _ = create_conversation()
    monkeypatch.setattr(settings, "WEBSOCKET_MAX_CONNECTIONS_PER_USER", 2)

    with client.websocket_connect(f"/ws/conversations/{conversation_id}?token={token}") as first:
        with client.websocket_connect(f"/ws/conversations/{conversation_id}?token={token}") as second:
            assert first is not None
            assert second is not None


def test_excess_connection_is_rejected_for_one_user(monkeypatch):
    conversation_id, token, _ = create_conversation()
    monkeypatch.setattr(settings, "WEBSOCKET_MAX_CONNECTIONS_PER_USER", 1)

    with client.websocket_connect(f"/ws/conversations/{conversation_id}?token={token}"):
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(f"/ws/conversations/{conversation_id}?token={token}"):
                pass


def test_connection_limit_does_not_affect_another_user(monkeypatch):
    conversation_id, first_token, second_token = create_conversation()
    monkeypatch.setattr(settings, "WEBSOCKET_MAX_CONNECTIONS_PER_USER", 1)

    with client.websocket_connect(f"/ws/conversations/{conversation_id}?token={first_token}"):
        with client.websocket_connect(f"/ws/conversations/{conversation_id}?token={second_token}") as websocket:
            assert websocket is not None


def test_disconnect_releases_connection_slot(monkeypatch):
    conversation_id, token, _ = create_conversation()
    monkeypatch.setattr(settings, "WEBSOCKET_MAX_CONNECTIONS_PER_USER", 1)

    with client.websocket_connect(f"/ws/conversations/{conversation_id}?token={token}"):
        pass
    with client.websocket_connect(f"/ws/conversations/{conversation_id}?token={token}") as websocket:
        assert websocket is not None


def test_stale_cleanup_releases_connection_slot():
    manager = ConnectionManager()
    websocket = type("FakeWebSocket", (), {"application_state": WebSocketState.DISCONNECTED})()
    manager.add_connection("conversation-1", websocket, "user-1")

    import asyncio
    asyncio.run(manager.broadcast("conversation-1", {"type": "message", "data": {}}))

    assert manager.get_user_connection_count("user-1") == 0
    assert manager.get_connections("conversation-1") == []


def test_message_below_limit_is_accepted_and_persisted(monkeypatch):
    conversation_id, token, _ = create_conversation()
    monkeypatch.setattr(settings, "WEBSOCKET_MAX_MESSAGE_SIZE_BYTES", 100)
    content = "a"
    message = json.dumps({"content": content}, separators=(",", ":"))

    with client.websocket_connect(f"/ws/conversations/{conversation_id}?token={token}") as websocket:
        websocket.send_text(message)
        acknowledgement = websocket.receive_json()

    assert acknowledgement["type"] == "message_ack"
    assert db.get_db()["messages"].count_documents({}) == 1


def test_message_at_exact_size_boundary_is_accepted(monkeypatch):
    conversation_id, token, _ = create_conversation()
    limit = 100
    monkeypatch.setattr(settings, "WEBSOCKET_MAX_MESSAGE_SIZE_BYTES", limit)
    content_length = limit - len(json.dumps({"content": ""}, separators=(",", ":")))
    message = json.dumps({"content": "a" * content_length}, separators=(",", ":"))
    assert len(message.encode("utf-8")) == limit

    with client.websocket_connect(f"/ws/conversations/{conversation_id}?token={token}") as websocket:
        websocket.send_text(message)
        acknowledgement = websocket.receive_json()

    assert acknowledgement["type"] == "message_ack"


def test_oversized_message_is_rejected_without_persistence_or_broadcast(monkeypatch):
    conversation_id, token, _ = create_conversation()
    monkeypatch.setattr(settings, "WEBSOCKET_MAX_MESSAGE_SIZE_BYTES", 20)

    with client.websocket_connect(f"/ws/conversations/{conversation_id}?token={token}") as websocket:
        websocket.send_text(json.dumps({"content": "x" * 100}))
        error = websocket.receive_json()

    assert error == {"type": "error", "data": {"detail": "WebSocket message is too large."}}
    assert db.get_db()["messages"].count_documents({}) == 0


def test_messages_under_rate_limit_are_accepted(monkeypatch):
    conversation_id, token, _ = create_conversation()
    monkeypatch.setattr(settings, "WEBSOCKET_MESSAGE_RATE_LIMIT", 2)

    with client.websocket_connect(f"/ws/conversations/{conversation_id}?token={token}") as websocket:
        for content in ["one", "two"]:
            websocket.send_json({"content": content})
            acknowledgement = websocket.receive_json()
            websocket.receive_json()
            assert acknowledgement["type"] == "message_ack"


def test_message_over_rate_limit_is_rejected_without_persistence(monkeypatch):
    conversation_id, token, _ = create_conversation()
    monkeypatch.setattr(settings, "WEBSOCKET_MESSAGE_RATE_LIMIT", 1)

    with client.websocket_connect(f"/ws/conversations/{conversation_id}?token={token}") as websocket:
        websocket.send_json({"content": "first"})
        websocket.receive_json()
        websocket.receive_json()
        websocket.send_json({"content": "second"})
        error = websocket.receive_json()

    assert error == {"type": "error", "data": {"detail": "Too many WebSocket messages. Try again later."}}
    assert db.get_db()["messages"].count_documents({}) == 1


def test_message_rate_limit_is_per_user(monkeypatch):
    conversation_id, first_token, second_token = create_conversation()
    monkeypatch.setattr(settings, "WEBSOCKET_MESSAGE_RATE_LIMIT", 1)

    with client.websocket_connect(f"/ws/conversations/{conversation_id}?token={first_token}") as first:
        with client.websocket_connect(f"/ws/conversations/{conversation_id}?token={second_token}") as second:
            first.send_json({"content": "first user"})
            first.receive_json()
            first.receive_json()
            second.send_json({"content": "second user"})
            second.receive_json()
            acknowledgement = second.receive_json()
            assert acknowledgement["type"] == "message_ack"
            first.receive_json()


def test_message_rate_limit_window_expiry_allows_message(monkeypatch):
    conversation_id, token, _ = create_conversation()
    current_time = 100.0
    monkeypatch.setattr("app.services.rate_limiter.time.monotonic", lambda: current_time)
    monkeypatch.setattr(settings, "WEBSOCKET_MESSAGE_RATE_LIMIT", 1)
    monkeypatch.setattr(settings, "WEBSOCKET_MESSAGE_RATE_WINDOW_SECONDS", 10)

    with client.websocket_connect(f"/ws/conversations/{conversation_id}?token={token}") as websocket:
        websocket.send_json({"content": "first"})
        websocket.receive_json()
        websocket.receive_json()
        current_time = 110.0
        websocket.send_json({"content": "after window"})
        acknowledgement = websocket.receive_json()

    assert acknowledgement["type"] == "message_ack"
