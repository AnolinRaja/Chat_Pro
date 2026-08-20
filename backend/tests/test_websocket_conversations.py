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


def test_authenticated_user_can_send_websocket_message():
    token1 = register_and_login(TEST_USERS[0])
    token2 = register_and_login(TEST_USERS[1])
    user2 = db.get_db()["users"].find_one({"email": TEST_USERS[1]["email"]})

    response = client.post(
        "/conversations",
        json={"other_user_id": str(user2["_id"])},
        headers={"Authorization": f"Bearer {token1}"},
    )
    conv_id = response.json()["id"]

    with client.websocket_connect(f"/ws/conversations/{conv_id}?token={token1}") as ws_one, \
         client.websocket_connect(f"/ws/conversations/{conv_id}?token={token2}") as ws_two:
        ws_one.send_json({"content": "Hello User B!"})
        acknowledgement = ws_one.receive_json()
        message_one = ws_one.receive_json()
        message_two = ws_two.receive_json()

        assert acknowledgement["type"] == "message_ack"
        assert acknowledgement["data"]["content"] == "Hello User B!"
        assert message_one["type"] == "message"
        assert message_two["type"] == "message"
        assert message_one["data"]["content"] == "Hello User B!"
        assert message_two["data"]["content"] == "Hello User B!"
        assert message_one["data"]["conversation_id"] == conv_id
        assert message_two["data"]["conversation_id"] == conv_id
        assert message_one["data"]["id"] == acknowledgement["data"]["id"]
        assert db.get_db()["messages"].count_documents({"conversation_id": ObjectId(conv_id)}) == 1


def test_websocket_invalid_message_is_rejected_safely():
    token1 = register_and_login(TEST_USERS[0])
    token2 = register_and_login(TEST_USERS[1])
    user2 = db.get_db()["users"].find_one({"email": TEST_USERS[1]["email"]})

    response = client.post(
        "/conversations",
        json={"other_user_id": str(user2["_id"])},
        headers={"Authorization": f"Bearer {token1}"},
    )
    conv_id = response.json()["id"]

    with client.websocket_connect(f"/ws/conversations/{conv_id}?token={token1}") as ws_one, \
         client.websocket_connect(f"/ws/conversations/{conv_id}?token={token2}") as ws_two:
        ws_one.send_json({"content": "   "})
        error_message = ws_one.receive_json()
        assert error_message["type"] == "error"
        assert "detail" in error_message["data"]

        ws_one.send_text("not-valid-json")
        invalid_json_error = ws_one.receive_json()
        assert invalid_json_error["type"] == "error"
        assert "detail" in invalid_json_error["data"]

        assert db.get_db()["messages"].count_documents({"conversation_id": ObjectId(conv_id)}) == 0
        assert len(connection_manager.get_connections(conv_id)) == 2


def test_websocket_ack_contains_persisted_message_fields():
    token1 = register_and_login(TEST_USERS[0])
    token2 = register_and_login(TEST_USERS[1])
    user2 = db.get_db()["users"].find_one({"email": TEST_USERS[1]["email"]})

    response = client.post(
        "/conversations",
        json={"other_user_id": str(user2["_id"])},
        headers={"Authorization": f"Bearer {token1}"},
    )
    conv_id = response.json()["id"]

    with client.websocket_connect(f"/ws/conversations/{conv_id}?token={token1}") as ws_one, \
         client.websocket_connect(f"/ws/conversations/{conv_id}?token={token2}") as ws_two:
        ws_one.send_json({"content": "Acknowledged message"})
        acknowledgement = ws_one.receive_json()
        broadcast = ws_one.receive_json()
        ws_two.receive_json()

        saved_message = acknowledgement["data"]
        assert acknowledgement["type"] == "message_ack"
        assert set(saved_message) == {"id", "conversation_id", "sender_id", "content", "created_at"}
        assert saved_message["conversation_id"] == conv_id
        assert saved_message["content"] == "Acknowledged message"
        assert broadcast == {"type": "message", "data": saved_message}


def test_websocket_missing_content_returns_error_without_persisting():
    token1 = register_and_login(TEST_USERS[0])
    token2 = register_and_login(TEST_USERS[1])
    user2 = db.get_db()["users"].find_one({"email": TEST_USERS[1]["email"]})

    response = client.post(
        "/conversations",
        json={"other_user_id": str(user2["_id"])},
        headers={"Authorization": f"Bearer {token1}"},
    )
    conv_id = response.json()["id"]

    with client.websocket_connect(f"/ws/conversations/{conv_id}?token={token1}") as ws_one, \
         client.websocket_connect(f"/ws/conversations/{conv_id}?token={token2}") as ws_two:
        ws_one.send_json({})
        error_event = ws_one.receive_json()

        assert error_event["type"] == "error"
        assert error_event["data"]["detail"] == "Invalid message payload."
        assert db.get_db()["messages"].count_documents({"conversation_id": ObjectId(conv_id)}) == 0
        assert len(connection_manager.get_connections(conv_id)) == 2


def test_non_participant_cannot_send_websocket_message():
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

    assert db.get_db()["messages"].count_documents({"conversation_id": ObjectId(conv_id)}) == 0


def test_rest_message_endpoints_still_work_after_ws_foundation():
    token1 = register_and_login(TEST_USERS[0])
    token2 = register_and_login(TEST_USERS[1])
    user2 = db.get_db()["users"].find_one({"email": TEST_USERS[1]["email"]})

    response = client.post(
        "/conversations",
        json={"other_user_id": str(user2["_id"])},
        headers={"Authorization": f"Bearer {token1}"},
    )
    conv_id = response.json()["id"]

    rest_response = client.post(
        f"/conversations/{conv_id}/messages",
        json={"content": "REST message"},
        headers={"Authorization": f"Bearer {token1}"},
    )

    assert rest_response.status_code == 201
    payload = rest_response.json()
    assert payload["content"] == "REST message"

    history = client.get(
        f"/conversations/{conv_id}/messages",
        headers={"Authorization": f"Bearer {token2}"},
    )
    assert history.status_code == 200
    assert history.json()[0]["content"] == "REST message"
