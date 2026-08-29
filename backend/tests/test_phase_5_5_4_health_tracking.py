"""
Phase 5.5.4: WebSocket Connection Health & Observability Tests
Tests for connection metadata tracking, idle detection, and lifecycle observability.
"""
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketState

from app.config import settings
from app.db import db
from app.main import app
from app.services.connection_manager import connection_manager

client = TestClient(app)

TEST_USERS = [
    {"name": "Health User 1", "email": "health_user1@example.com", "password": "Password123"},
    {"name": "Health User 2", "email": "health_user2@example.com", "password": "Password123"},
]


@pytest.fixture(autouse=True)
def cleanup_health_test_data():
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
    client.post("/auth/register/verify", json={"email": user_data["email"], "otp": "123456"})
    response = client.post("/auth/login", json={"email": user_data["email"], "password": user_data["password"]})
    return client.post("/auth/login/verify", json={"email": user_data["email"], "otp": "123456"}).json()["access_token"]


# === Phase 5.5.4: Connection Metadata Registration ===

def test_connection_metadata_is_registered_with_user_id():
    """Verify that connection metadata is stored when a WebSocket connects."""
    from starlette.websockets import WebSocket
    
    token1 = register_and_login(TEST_USERS[0])
    token2 = register_and_login(TEST_USERS[1])
    user2 = db.get_db()["users"].find_one({"email": TEST_USERS[1]["email"]})
    response = client.post(
        "/conversations",
        json={"other_user_id": str(user2["_id"])},
        headers={"Authorization": f"Bearer {token1}"},
    )
    conversation_id = response.json()["id"]
    user1 = db.get_db()["users"].find_one({"email": TEST_USERS[0]["email"]})

    with client.websocket_connect(f"/ws/conversations/{conversation_id}?token={token1}") as websocket:
        connections = connection_manager.get_connections(conversation_id)
        assert len(connections) == 1
        ws = connections[0]
        metadata = connection_manager._metadata.get(ws)
        assert metadata is not None
        assert metadata["conversation_id"] == conversation_id
        assert metadata["user_id"] == str(user1["_id"])
        assert metadata["connected_at"] is not None
        assert metadata["last_activity"] is not None


def test_last_activity_is_initialized_on_connection():
    """Verify that last_activity is set when connection is established."""
    token1 = register_and_login(TEST_USERS[0])
    token2 = register_and_login(TEST_USERS[1])
    user2 = db.get_db()["users"].find_one({"email": TEST_USERS[1]["email"]})
    response = client.post(
        "/conversations",
        json={"other_user_id": str(user2["_id"])},
        headers={"Authorization": f"Bearer {token1}"},
    )
    conversation_id = response.json()["id"]

    with client.websocket_connect(f"/ws/conversations/{conversation_id}?token={token1}") as websocket:
        ws = connection_manager.get_connections(conversation_id)[0]
        metadata = connection_manager._metadata.get(ws)
        connected_at = metadata["connected_at"]
        last_activity = metadata["last_activity"]
        assert connected_at is not None
        assert last_activity is not None
        # Both should be set at initialization (within 1 second)
        assert abs((last_activity - connected_at).total_seconds()) < 1


def test_activity_updates_last_activity_timestamp():
    """Verify that last_activity is updated when WebSocket receives messages."""
    token1 = register_and_login(TEST_USERS[0])
    token2 = register_and_login(TEST_USERS[1])
    user2 = db.get_db()["users"].find_one({"email": TEST_USERS[1]["email"]})
    response = client.post(
        "/conversations",
        json={"other_user_id": str(user2["_id"])},
        headers={"Authorization": f"Bearer {token1}"},
    )
    conversation_id = response.json()["id"]

    with client.websocket_connect(f"/ws/conversations/{conversation_id}?token={token1}") as websocket:
        ws = connection_manager.get_connections(conversation_id)[0]
        initial_activity = connection_manager._metadata[ws]["last_activity"]

        # Wait briefly to ensure time difference is measurable
        import time
        time.sleep(0.1)

        websocket.send_json({"content": "update activity test"})
        ack = websocket.receive_json()  # Get message_ack
        
        updated_activity = connection_manager._metadata[ws]["last_activity"]
        assert updated_activity > initial_activity


def test_disconnected_connections_are_removed_from_metadata():
    """Verify that metadata is cleaned up when connection is removed."""
    token1 = register_and_login(TEST_USERS[0])
    token2 = register_and_login(TEST_USERS[1])
    user2 = db.get_db()["users"].find_one({"email": TEST_USERS[1]["email"]})
    response = client.post(
        "/conversations",
        json={"other_user_id": str(user2["_id"])},
        headers={"Authorization": f"Bearer {token1}"},
    )
    conversation_id = response.json()["id"]

    with client.websocket_connect(f"/ws/conversations/{conversation_id}?token={token1}") as websocket:
        ws = connection_manager.get_connections(conversation_id)[0]
        assert ws in connection_manager._metadata

    # After exiting context, connection should be removed
    assert len(connection_manager.get_connections(conversation_id)) == 0
    # All metadata should be cleaned
    assert len(connection_manager._metadata) == 0


# === Phase 5.5.4: Health Statistics ===

def test_get_conversation_stats_returns_correct_total_connections():
    """Verify that get_conversation_stats correctly counts total connections."""
    token1 = register_and_login(TEST_USERS[0])
    token2 = register_and_login(TEST_USERS[1])
    user2 = db.get_db()["users"].find_one({"email": TEST_USERS[1]["email"]})
    response = client.post(
        "/conversations",
        json={"other_user_id": str(user2["_id"])},
        headers={"Authorization": f"Bearer {token1}"},
    )
    conversation_id = response.json()["id"]

    with client.websocket_connect(f"/ws/conversations/{conversation_id}?token={token1}") as ws_one:
        with client.websocket_connect(f"/ws/conversations/{conversation_id}?token={token2}") as ws_two:
            stats = connection_manager.get_conversation_stats(conversation_id)
            assert stats["total_connections"] == 2


def test_get_conversation_stats_counts_healthy_connections():
    """Verify that healthy (non-idle) connections are counted correctly."""
    token1 = register_and_login(TEST_USERS[0])
    token2 = register_and_login(TEST_USERS[1])
    user2 = db.get_db()["users"].find_one({"email": TEST_USERS[1]["email"]})
    response = client.post(
        "/conversations",
        json={"other_user_id": str(user2["_id"])},
        headers={"Authorization": f"Bearer {token1}"},
    )
    conversation_id = response.json()["id"]

    with client.websocket_connect(f"/ws/conversations/{conversation_id}?token={token1}") as ws_one:
        with client.websocket_connect(f"/ws/conversations/{conversation_id}?token={token2}") as ws_two:
            stats = connection_manager.get_conversation_stats(conversation_id)
            assert stats["total_connections"] == 2
            assert stats["healthy_connections"] == 2
            assert stats["idle_connections"] == 0


def test_get_conversation_stats_identifies_idle_connections():
    """Verify that idle connections are identified based on idle threshold."""
    token1 = register_and_login(TEST_USERS[0])
    token2 = register_and_login(TEST_USERS[1])
    user2 = db.get_db()["users"].find_one({"email": TEST_USERS[1]["email"]})
    response = client.post(
        "/conversations",
        json={"other_user_id": str(user2["_id"])},
        headers={"Authorization": f"Bearer {token1}"},
    )
    conversation_id = response.json()["id"]

    with client.websocket_connect(f"/ws/conversations/{conversation_id}?token={token1}") as ws_one:
        with client.websocket_connect(f"/ws/conversations/{conversation_id}?token={token2}") as ws_two:
            # Manually set last_activity for one connection to be in the past
            ws = connection_manager.get_connections(conversation_id)[0]
            old_time = datetime.now(timezone.utc) - timedelta(seconds=settings.WEBSOCKET_IDLE_THRESHOLD_SECONDS + 1)
            connection_manager._metadata[ws]["last_activity"] = old_time

            stats = connection_manager.get_conversation_stats(conversation_id)
            assert stats["total_connections"] == 2
            assert stats["healthy_connections"] == 1
            assert stats["idle_connections"] == 1


def test_get_conversation_stats_empty_conversation():
    """Verify that stats for a non-existent conversation return zeros."""
    stats = connection_manager.get_conversation_stats("non-existent-conversation")
    assert stats["total_connections"] == 0
    assert stats["healthy_connections"] == 0
    assert stats["idle_connections"] == 0


# === Phase 5.5.4: Lifecycle Logging ===

def test_connection_lifecycle_logging_contains_conversation_and_user_ids(caplog):
    """Verify that lifecycle logs contain conversation_id and user_id."""
    import logging
    token1 = register_and_login(TEST_USERS[0])
    token2 = register_and_login(TEST_USERS[1])
    user2 = db.get_db()["users"].find_one({"email": TEST_USERS[1]["email"]})
    response = client.post(
        "/conversations",
        json={"other_user_id": str(user2["_id"])},
        headers={"Authorization": f"Bearer {token1}"},
    )
    conversation_id = response.json()["id"]
    user1 = db.get_db()["users"].find_one({"email": TEST_USERS[0]["email"]})

    with caplog.at_level(logging.INFO):
        with client.websocket_connect(f"/ws/conversations/{conversation_id}?token={token1}"):
            pass

    # Log should contain connection_id and user_id for established and removed
    assert conversation_id in caplog.text
    assert str(user1["_id"]) in caplog.text


def test_lifecycle_logs_do_not_contain_jwt_tokens(caplog):
    """Verify that JWT tokens are never logged."""
    import logging
    token1 = register_and_login(TEST_USERS[0])
    token2 = register_and_login(TEST_USERS[1])
    user2 = db.get_db()["users"].find_one({"email": TEST_USERS[1]["email"]})
    response = client.post(
        "/conversations",
        json={"other_user_id": str(user2["_id"])},
        headers={"Authorization": f"Bearer {token1}"},
    )
    conversation_id = response.json()["id"]

    with caplog.at_level(logging.INFO):
        with client.websocket_connect(f"/ws/conversations/{conversation_id}?token={token1}"):
            pass

    # Token should NOT appear in logs
    assert token1 not in caplog.text
    # Authorization header should NOT appear in logs
    assert "authorization" not in caplog.text.lower() or "bearer" not in caplog.text.lower()


def test_lifecycle_logs_do_not_contain_message_contents(caplog):
    """Verify that message contents are never logged."""
    import logging
    token1 = register_and_login(TEST_USERS[0])
    token2 = register_and_login(TEST_USERS[1])
    user2 = db.get_db()["users"].find_one({"email": TEST_USERS[1]["email"]})
    response = client.post(
        "/conversations",
        json={"other_user_id": str(user2["_id"])},
        headers={"Authorization": f"Bearer {token1}"},
    )
    conversation_id = response.json()["id"]
    
    secret_message = "this-is-a-secret-message-content"

    with caplog.at_level(logging.INFO):
        with client.websocket_connect(f"/ws/conversations/{conversation_id}?token={token1}") as ws_one:
            with client.websocket_connect(f"/ws/conversations/{conversation_id}?token={token2}") as ws_two:
                ws_one.send_json({"content": secret_message})
                ws_one.receive_json()  # ACK
                ws_two.receive_json()  # Message

    # Secret message content should NOT appear in logs
    assert secret_message not in caplog.text


# === Phase 5.5.4: Existing Functionality Preservation ===

def test_messaging_still_works_with_metadata_tracking():
    """Verify that existing WebSocket messaging is unaffected by health tracking."""
    token1 = register_and_login(TEST_USERS[0])
    token2 = register_and_login(TEST_USERS[1])
    user2 = db.get_db()["users"].find_one({"email": TEST_USERS[1]["email"]})
    response = client.post(
        "/conversations",
        json={"other_user_id": str(user2["_id"])},
        headers={"Authorization": f"Bearer {token1}"},
    )
    conversation_id = response.json()["id"]

    with client.websocket_connect(f"/ws/conversations/{conversation_id}?token={token1}") as ws_one:
        with client.websocket_connect(f"/ws/conversations/{conversation_id}?token={token2}") as ws_two:
            ws_one.send_json({"content": "health tracking test message"})
            ack = ws_one.receive_json()
            assert ack["type"] == "message_ack"
            msg = ws_two.receive_json()
            assert msg["type"] == "message"
            assert msg["data"]["content"] == "health tracking test message"


def test_broadcasting_not_affected_by_activity_tracking():
    """Verify that concurrent broadcasting continues to work correctly."""
    token1 = register_and_login(TEST_USERS[0])
    token2 = register_and_login(TEST_USERS[1])
    user2 = db.get_db()["users"].find_one({"email": TEST_USERS[1]["email"]})
    response = client.post(
        "/conversations",
        json={"other_user_id": str(user2["_id"])},
        headers={"Authorization": f"Bearer {token1}"},
    )
    conversation_id = response.json()["id"]

    with client.websocket_connect(f"/ws/conversations/{conversation_id}?token={token1}") as ws_one:
        with client.websocket_connect(f"/ws/conversations/{conversation_id}?token={token2}") as ws_two:
            with client.websocket_connect(f"/ws/conversations/{conversation_id}?token={token1}") as ws_three:
                ws_one.send_json({"content": "broadcast test"})
                ws_one.receive_json()  # ACK
                msg_two = ws_two.receive_json()
                msg_three = ws_three.receive_json()
                assert msg_two["data"]["content"] == "broadcast test"
                assert msg_three["data"]["content"] == "broadcast test"


def test_rest_apis_unaffected_by_websocket_health_tracking():
    """Verify that REST endpoints continue to work as before."""
    token1 = register_and_login(TEST_USERS[0])
    token2 = register_and_login(TEST_USERS[1])
    user2 = db.get_db()["users"].find_one({"email": TEST_USERS[1]["email"]})

    # Create conversation (existing REST endpoint)
    response = client.post(
        "/conversations",
        json={"other_user_id": str(user2["_id"])},
        headers={"Authorization": f"Bearer {token1}"},
    )
    assert response.status_code == 201
    conversation_id = response.json()["id"]

    # Send message via REST (existing endpoint)
    response = client.post(
        f"/conversations/{conversation_id}/messages",
        json={"content": "REST API test message"},
        headers={"Authorization": f"Bearer {token1}"},
    )
    assert response.status_code == 201

    # List messages (existing endpoint)
    response = client.get(
        f"/conversations/{conversation_id}/messages",
        headers={"Authorization": f"Bearer {token1}"},
    )
    assert response.status_code == 200
    messages = response.json()
    assert len(messages) == 1
    assert messages[0]["content"] == "REST API test message"


def test_authentication_and_authorization_unchanged_with_health_tracking():
    """Verify that auth/authz behavior remains unchanged."""
    token1 = register_and_login(TEST_USERS[0])
    token2 = register_and_login(TEST_USERS[1])
    user2 = db.get_db()["users"].find_one({"email": TEST_USERS[1]["email"]})
    response = client.post(
        "/conversations",
        json={"other_user_id": str(user2["_id"])},
        headers={"Authorization": f"Bearer {token1}"},
    )
    conversation_id = response.json()["id"]

    # Valid tokens should work
    with client.websocket_connect(f"/ws/conversations/{conversation_id}?token={token1}"):
        pass

    with client.websocket_connect(f"/ws/conversations/{conversation_id}?token={token2}"):
        pass

    # Invalid token should be rejected
    import pytest
    with pytest.raises(Exception):
        with client.websocket_connect(f"/ws/conversations/{conversation_id}?token=invalid-token"):
            pass
