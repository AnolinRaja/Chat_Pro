import pytest
from starlette.websockets import WebSocketState

from app.services.connection_manager import ConnectionManager


class FakeWebSocket:
    def __init__(self, state=WebSocketState.CONNECTED):
        self.application_state = state

    async def send_json(self, payload):
        pass


def test_same_websocket_cannot_be_registered_to_another_conversation():
    manager = ConnectionManager()
    websocket = FakeWebSocket()
    manager.add_connection("conversation-a", websocket, "user-a")

    with pytest.raises(ValueError, match="already registered to a different conversation"):
        manager.add_connection("conversation-b", websocket, "user-b")

    assert manager.get_connections("conversation-a") == [websocket]
    assert manager.get_connections("conversation-b") == []


def test_rejected_registration_does_not_change_existing_metadata():
    manager = ConnectionManager()
    websocket = FakeWebSocket()
    manager.add_connection("conversation-a", websocket, "user-a")
    original_metadata = manager._metadata[websocket].copy()

    with pytest.raises(ValueError):
        manager.add_connection("conversation-b", websocket, "user-b")

    assert manager._metadata[websocket] == original_metadata
    assert manager._metadata[websocket]["conversation_id"] == "conversation-a"
    assert manager._metadata[websocket]["user_id"] == "user-a"
    assert "conversation-b" not in manager._connections


def test_same_websocket_can_be_registered_repeatedly_to_same_conversation():
    manager = ConnectionManager()
    websocket = FakeWebSocket()

    manager.add_connection("conversation-a", websocket)
    manager.add_connection("conversation-a", websocket)

    assert manager.get_connections("conversation-a") == [websocket]
    assert len(manager._metadata) == 1
    assert manager._metadata[websocket]["conversation_id"] == "conversation-a"


def test_valid_websockets_can_register_to_separate_conversations():
    manager = ConnectionManager()
    first = FakeWebSocket()
    second = FakeWebSocket()

    manager.add_connection("conversation-a", first, "user-a")
    manager.add_connection("conversation-b", second, "user-b")

    assert manager.get_connections("conversation-a") == [first]
    assert manager.get_connections("conversation-b") == [second]
    assert manager._metadata[first]["user_id"] == "user-a"
    assert manager._metadata[second]["user_id"] == "user-b"


def test_removal_after_rejected_registration_cleans_original_connection():
    manager = ConnectionManager()
    websocket = FakeWebSocket()
    manager.add_connection("conversation-a", websocket, "user-a")

    with pytest.raises(ValueError):
        manager.add_connection("conversation-b", websocket, "user-b")

    manager.remove_connection("conversation-a", websocket)

    assert manager.get_connections("conversation-a") == []
    assert manager.get_connections("conversation-b") == []
    assert websocket not in manager._metadata


def test_health_stats_remain_consistent_after_rejected_registration():
    manager = ConnectionManager()
    websocket = FakeWebSocket()
    manager.add_connection("conversation-a", websocket, "user-a")

    with pytest.raises(ValueError):
        manager.add_connection("conversation-b", websocket, "user-b")

    assert manager.get_conversation_stats("conversation-a") == {
        "total_connections": 1,
        "healthy_connections": 1,
        "idle_connections": 0,
    }
    assert manager.get_conversation_stats("conversation-b") == {
        "total_connections": 0,
        "healthy_connections": 0,
        "idle_connections": 0,
    }
