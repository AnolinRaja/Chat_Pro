import asyncio
from unittest.mock import AsyncMock

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect, WebSocketState

from app.db import db
from app.main import app
from app.services.connection_manager import connection_manager
from app.services.message_service import MessageService

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


def test_sequential_websocket_messages_preserve_order_and_persist_each_message():
    token1 = register_and_login(TEST_USERS[0])
    token2 = register_and_login(TEST_USERS[1])
    user2 = db.get_db()["users"].find_one({"email": TEST_USERS[1]["email"]})

    response = client.post(
        "/conversations",
        json={"other_user_id": str(user2["_id"])},
        headers={"Authorization": f"Bearer {token1}"},
    )
    conv_id = response.json()["id"]

    contents = ["First message", "Second message", "Third message"]

    with client.websocket_connect(f"/ws/conversations/{conv_id}?token={token1}") as ws_one, \
         client.websocket_connect(f"/ws/conversations/{conv_id}?token={token2}") as ws_two:
        for content in contents:
            ws_one.send_json({"content": content})

            acknowledgement = ws_one.receive_json()
            sender_message = ws_one.receive_json()
            recipient_message = ws_two.receive_json()

            assert acknowledgement["type"] == "message_ack"
            assert acknowledgement["data"]["content"] == content
            assert sender_message["type"] == "message"
            assert recipient_message["type"] == "message"
            assert sender_message["data"]["content"] == content
            assert recipient_message["data"]["content"] == content
            assert sender_message["data"]["id"] == acknowledgement["data"]["id"]

    stored_messages = list(
        db.get_db()["messages"].find({"conversation_id": ObjectId(conv_id)}).sort("created_at", 1)
    )
    assert [message["content"] for message in stored_messages] == contents


def test_messages_are_isolated_between_conversations():
    token1 = register_and_login(TEST_USERS[0])
    token2 = register_and_login(TEST_USERS[1])
    token3 = register_and_login(TEST_USERS[2])
    user2 = db.get_db()["users"].find_one({"email": TEST_USERS[1]["email"]})
    user3 = db.get_db()["users"].find_one({"email": TEST_USERS[2]["email"]})

    conversation_a = client.post(
        "/conversations",
        json={"other_user_id": str(user2["_id"])},
        headers={"Authorization": f"Bearer {token1}"},
    ).json()["id"]
    conversation_b = client.post(
        "/conversations",
        json={"other_user_id": str(user3["_id"])},
        headers={"Authorization": f"Bearer {token2}"},
    ).json()["id"]

    with client.websocket_connect(f"/ws/conversations/{conversation_a}?token={token1}") as ws_a_one, \
         client.websocket_connect(f"/ws/conversations/{conversation_a}?token={token2}") as ws_a_two, \
         client.websocket_connect(f"/ws/conversations/{conversation_b}?token={token2}") as ws_b_one, \
         client.websocket_connect(f"/ws/conversations/{conversation_b}?token={token3}") as ws_b_two:
        ws_a_one.send_json({"content": "Conversation A message"})
        ws_a_one.receive_json()
        conversation_a_sender_event = ws_a_one.receive_json()
        conversation_a_recipient_event = ws_a_two.receive_json()

        assert conversation_a_sender_event["type"] == "message"
        assert conversation_a_recipient_event["type"] == "message"
        assert conversation_a_sender_event["data"]["content"] == "Conversation A message"
        assert conversation_a_recipient_event["data"]["content"] == "Conversation A message"

        ws_b_one.send_json({"content": "Conversation B message"})
        conversation_b_ack = ws_b_one.receive_json()
        conversation_b_sender_event = ws_b_one.receive_json()
        conversation_b_recipient_event = ws_b_two.receive_json()

        assert conversation_b_ack["type"] == "message_ack"
        assert conversation_b_sender_event["type"] == "message"
        assert conversation_b_recipient_event["type"] == "message"
        assert conversation_b_ack["data"]["conversation_id"] == conversation_b
        assert conversation_b_sender_event["data"]["content"] == "Conversation B message"
        assert conversation_b_recipient_event["data"]["content"] == "Conversation B message"


def test_connection_remains_usable_after_invalid_message_error():
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
        ws_one.send_text("not-valid-json")
        invalid_json_error = ws_one.receive_json()
        assert invalid_json_error["type"] == "error"

        ws_one.send_json({"content": "   "})
        invalid_message_error = ws_one.receive_json()
        assert invalid_message_error["type"] == "error"

        ws_one.send_json({"content": "Valid after errors"})
        acknowledgement = ws_one.receive_json()
        sender_event = ws_one.receive_json()
        recipient_event = ws_two.receive_json()

        assert acknowledgement["type"] == "message_ack"
        assert sender_event["type"] == "message"
        assert recipient_event["type"] == "message"
        assert acknowledgement["data"]["content"] == "Valid after errors"
        assert sender_event["data"]["content"] == "Valid after errors"
        assert recipient_event["data"]["content"] == "Valid after errors"
        assert db.get_db()["messages"].count_documents({"conversation_id": ObjectId(conv_id)}) == 1


def test_disconnect_removes_one_participant_and_keeps_other_connected():
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
        with client.websocket_connect(f"/ws/conversations/{conv_id}?token={token2}"):
            assert len(connection_manager.get_connections(conv_id)) == 2

        assert len(connection_manager.get_connections(conv_id)) == 1
        ws_one.send_json({"content": "Remaining participant message"})

        acknowledgement = ws_one.receive_json()
        message_event = ws_one.receive_json()
        assert acknowledgement["type"] == "message_ack"
        assert message_event["type"] == "message"
        assert message_event["data"]["content"] == "Remaining participant message"

    assert len(connection_manager.get_connections(conv_id)) == 0


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


class _BroadcastTestWebSocket:
    def __init__(self, *, state=WebSocketState.CONNECTED, error=None, started=None, release=None):
        self.application_state = state
        self.error = error
        self.messages = []
        self.started = started
        self.release = release

    async def send_json(self, message):
        if self.started is not None:
            self.started.set()
        if self.release is not None:
            await self.release.wait()
        if self.error is not None:
            raise self.error
        self.messages.append(message)


def test_broadcast_failure_isolated_and_failed_client_removed():
    conversation_id = "broadcast-failure"
    healthy_websocket = _BroadcastTestWebSocket()
    failed_websocket = _BroadcastTestWebSocket(error=RuntimeError("send failed"))
    connection_manager.add_connection(conversation_id, healthy_websocket)
    connection_manager.add_connection(conversation_id, failed_websocket)

    event = {"type": "message", "data": {"content": "still delivered"}}
    asyncio.run(connection_manager.broadcast(conversation_id, event))

    assert healthy_websocket.messages == [event]
    assert connection_manager.get_connections(conversation_id) == [healthy_websocket]


def test_broadcast_removes_disconnected_client_and_reaches_connected_client():
    conversation_id = "broadcast-disconnect"
    healthy_websocket = _BroadcastTestWebSocket()
    disconnected_websocket = _BroadcastTestWebSocket(state=WebSocketState.DISCONNECTED)
    connection_manager.add_connection(conversation_id, healthy_websocket, None)
    connection_manager.add_connection(conversation_id, disconnected_websocket, None)

    event = {"type": "message", "data": {"content": "healthy only"}}
    asyncio.run(connection_manager.broadcast(conversation_id, event))

    assert healthy_websocket.messages == [event]
    assert connection_manager.get_connections(conversation_id) == [healthy_websocket]


def test_broadcast_sends_to_clients_concurrently():
    conversation_id = "broadcast-concurrent"
    slow_started = asyncio.Event()
    slow_release = asyncio.Event()
    slow_websocket = _BroadcastTestWebSocket(started=slow_started, release=slow_release)
    healthy_websocket = _BroadcastTestWebSocket()
    connection_manager.add_connection(conversation_id, slow_websocket, None)
    connection_manager.add_connection(conversation_id, healthy_websocket, None)

    event = {"type": "message", "data": {"content": "concurrent delivery"}}

    async def broadcast_while_slow_client_waits():
        broadcast_task = asyncio.create_task(connection_manager.broadcast(conversation_id, event))
        await asyncio.wait_for(slow_started.wait(), timeout=1)
        await asyncio.sleep(0)
        assert healthy_websocket.messages == [event]
        slow_release.set()
        await asyncio.wait_for(broadcast_task, timeout=1)

    asyncio.run(broadcast_while_slow_client_waits())


def test_slow_and_failed_clients_do_not_block_healthy_broadcast_delivery():
    conversation_id = "broadcast-slow-failure"
    slow_started = asyncio.Event()
    slow_release = asyncio.Event()
    slow_websocket = _BroadcastTestWebSocket(started=slow_started, release=slow_release)
    failed_websocket = _BroadcastTestWebSocket(error=RuntimeError("send failed"))
    healthy_websocket = _BroadcastTestWebSocket()
    connection_manager.add_connection(conversation_id, slow_websocket, None)
    connection_manager.add_connection(conversation_id, failed_websocket, None)
    connection_manager.add_connection(conversation_id, healthy_websocket, None)

    event = {"type": "message", "data": {"content": "isolated delivery"}}

    async def broadcast_with_slow_and_failed_clients():
        broadcast_task = asyncio.create_task(connection_manager.broadcast(conversation_id, event))
        await asyncio.wait_for(slow_started.wait(), timeout=1)
        await asyncio.sleep(0)
        assert healthy_websocket.messages == [event]
        slow_release.set()
        await asyncio.wait_for(broadcast_task, timeout=1)

    asyncio.run(broadcast_with_slow_and_failed_clients())

    assert connection_manager.get_connections(conversation_id) == [slow_websocket, healthy_websocket]


def test_unexpected_persistence_exception_returns_safe_error_and_is_logged(monkeypatch, caplog):
    token1 = register_and_login(TEST_USERS[0])
    token2 = register_and_login(TEST_USERS[1])
    user2 = db.get_db()["users"].find_one({"email": TEST_USERS[1]["email"]})
    response = client.post(
        "/conversations",
        json={"other_user_id": str(user2["_id"])},
        headers={"Authorization": f"Bearer {token1}"},
    )
    conversation_id = response.json()["id"]
    failure_detail = "database internals must not be exposed"
    message_content = "secret message content"

    def fail_persistence(*args, **kwargs):
        raise RuntimeError(failure_detail)

    monkeypatch.setattr(MessageService, "send_message", fail_persistence)

    with caplog.at_level("ERROR"):
        with client.websocket_connect(f"/ws/conversations/{conversation_id}?token={token1}") as websocket:
            websocket.send_json({"content": message_content})
            error_event = websocket.receive_json()

    assert error_event == {
        "type": "error",
        "data": {"detail": "Unable to send message."},
    }
    assert failure_detail in caplog.text
    assert token1 not in caplog.text
    assert message_content not in caplog.text
    assert conversation_id in caplog.text


def test_persistence_failure_does_not_ack_broadcast_or_create_message(monkeypatch):
    token1 = register_and_login(TEST_USERS[0])
    token2 = register_and_login(TEST_USERS[1])
    user2 = db.get_db()["users"].find_one({"email": TEST_USERS[1]["email"]})
    response = client.post(
        "/conversations",
        json={"other_user_id": str(user2["_id"])},
        headers={"Authorization": f"Bearer {token1}"},
    )
    conversation_id = response.json()["id"]
    broadcast_mock = AsyncMock()

    monkeypatch.setattr(MessageService, "send_message", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("failed")))
    monkeypatch.setattr(connection_manager, "broadcast", broadcast_mock)

    with client.websocket_connect(f"/ws/conversations/{conversation_id}?token={token1}") as websocket:
        websocket.send_json({"content": "not persisted"})
        error_event = websocket.receive_json()

    assert error_event["type"] == "error"
    assert error_event["data"]["detail"] == "Unable to send message."
    broadcast_mock.assert_not_awaited()
    assert db.get_db()["messages"].count_documents({"conversation_id": ObjectId(conversation_id)}) == 0


def test_connection_remains_usable_after_recoverable_persistence_failure(monkeypatch):
    token1 = register_and_login(TEST_USERS[0])
    token2 = register_and_login(TEST_USERS[1])
    user2 = db.get_db()["users"].find_one({"email": TEST_USERS[1]["email"]})
    response = client.post(
        "/conversations",
        json={"other_user_id": str(user2["_id"])},
        headers={"Authorization": f"Bearer {token1}"},
    )
    conversation_id = response.json()["id"]
    original_send_message = MessageService.send_message
    attempts = 0

    def fail_once_then_persist(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("temporary persistence failure")
        return original_send_message(*args, **kwargs)

    monkeypatch.setattr(MessageService, "send_message", fail_once_then_persist)

    with client.websocket_connect(f"/ws/conversations/{conversation_id}?token={token1}") as ws_one, \
         client.websocket_connect(f"/ws/conversations/{conversation_id}?token={token2}") as ws_two:
        ws_one.send_json({"content": "first attempt"})
        error_event = ws_one.receive_json()
        assert error_event["type"] == "error"

        ws_one.send_json({"content": "successful retry"})
        acknowledgement = ws_one.receive_json()
        sender_event = ws_one.receive_json()
        recipient_event = ws_two.receive_json()

        assert acknowledgement["type"] == "message_ack"
        assert sender_event["type"] == "message"
        assert recipient_event["type"] == "message"
        assert sender_event["data"]["content"] == "successful retry"
        assert recipient_event["data"]["content"] == "successful retry"

    assert db.get_db()["messages"].count_documents({"conversation_id": ObjectId(conversation_id)}) == 1


def test_unexpected_outer_websocket_exception_is_logged_and_connection_cleaned(monkeypatch, caplog):
    token1 = register_and_login(TEST_USERS[0])
    token2 = register_and_login(TEST_USERS[1])
    user2 = db.get_db()["users"].find_one({"email": TEST_USERS[1]["email"]})
    response = client.post(
        "/conversations",
        json={"other_user_id": str(user2["_id"])},
        headers={"Authorization": f"Bearer {token1}"},
    )
    conversation_id = response.json()["id"]
    unexpected_detail = "unexpected websocket internals"

    async def fail_receive_text(self):
        raise RuntimeError(unexpected_detail)

    monkeypatch.setattr("starlette.websockets.WebSocket.receive_text", fail_receive_text)

    with caplog.at_level("ERROR"):
        with client.websocket_connect(f"/ws/conversations/{conversation_id}?token={token1}"):
            pass

    assert unexpected_detail in caplog.text
    assert conversation_id in caplog.text
    assert len(connection_manager.get_connections(conversation_id)) == 0


def test_invalid_authentication_is_not_written_to_logs(caplog):
    sensitive_token = "sensitive-access-token-value"
    with caplog.at_level("ERROR"):
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(f"/ws/conversations/{ObjectId()}?token={sensitive_token}"):
                pass

    assert sensitive_token not in caplog.text
