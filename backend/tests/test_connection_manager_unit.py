import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from starlette.websockets import WebSocketState

from app.services.connection_manager import ConnectionManager


class FakeWebSocket:
    def __init__(self, *, state=WebSocketState.CONNECTED, error=None, started=None, release=None):
        self.application_state = state
        self.error = error
        self.messages = []
        self.started = started
        self.release = release

    async def send_json(self, payload):
        if self.started is not None:
            self.started.set()
        if self.release is not None:
            await self.release.wait()
        if self.error is not None:
            raise self.error
        self.messages.append(payload)


@pytest.fixture
def manager():
    return ConnectionManager()


def test_add_connection_registers_connection_and_metadata(manager):
    websocket = FakeWebSocket()

    manager.add_connection("conversation-1", websocket, "user-1")

    assert manager.get_connections("conversation-1") == [websocket]
    metadata = manager._metadata[websocket]
    assert metadata["conversation_id"] == "conversation-1"
    assert metadata["user_id"] == "user-1"
    assert metadata["connected_at"].tzinfo == timezone.utc
    assert metadata["last_activity"] == metadata["connected_at"]


def test_add_connection_accepts_missing_user_id(manager):
    websocket = FakeWebSocket()

    manager.add_connection("conversation-1", websocket)

    assert manager._metadata[websocket]["user_id"] is None


def test_duplicate_add_does_not_duplicate_registration(manager):
    websocket = FakeWebSocket()

    manager.add_connection("conversation-1", websocket, "user-1")
    manager.add_connection("conversation-1", websocket, "user-1")

    assert manager.get_connections("conversation-1") == [websocket]
    assert len(manager._metadata) == 1


def test_remove_connection_removes_existing_connection_and_metadata(manager):
    websocket = FakeWebSocket()
    manager.add_connection("conversation-1", websocket, "user-1")

    manager.remove_connection("conversation-1", websocket)

    assert manager.get_connections("conversation-1") == []
    assert websocket not in manager._metadata


def test_remove_connection_missing_conversation_is_safe(manager):
    websocket = FakeWebSocket()

    manager.remove_connection("missing", websocket)

    assert manager.get_connections("missing") == []


def test_remove_connection_missing_websocket_is_safe(manager):
    registered = FakeWebSocket()
    missing = FakeWebSocket()
    manager.add_connection("conversation-1", registered)

    manager.remove_connection("conversation-1", missing)

    assert manager.get_connections("conversation-1") == [registered]
    assert registered in manager._metadata


def test_remove_connection_removes_final_conversation_entry(manager):
    websocket = FakeWebSocket()
    manager.add_connection("conversation-1", websocket)

    manager.remove_connection("conversation-1", websocket)

    assert "conversation-1" not in manager._connections


def test_get_connections_returns_registered_connections(manager):
    first = FakeWebSocket()
    second = FakeWebSocket()
    manager.add_connection("conversation-1", first)
    manager.add_connection("conversation-1", second)

    assert manager.get_connections("conversation-1") == [first, second]


def test_get_connections_returns_independent_list(manager):
    websocket = FakeWebSocket()
    manager.add_connection("conversation-1", websocket)

    returned = manager.get_connections("conversation-1")
    returned.clear()

    assert manager.get_connections("conversation-1") == [websocket]


def test_get_connections_empty_conversation_returns_empty_list(manager):
    assert manager.get_connections("missing") == []


def test_update_activity_changes_existing_connection_timestamp(manager):
    websocket = FakeWebSocket()
    manager.add_connection("conversation-1", websocket)
    initial_activity = manager._metadata[websocket]["last_activity"]

    manager.update_activity(websocket)

    assert manager._metadata[websocket]["last_activity"] >= initial_activity


def test_update_activity_missing_connection_is_safe(manager):
    manager.update_activity(FakeWebSocket())

    assert manager._metadata == {}


def test_stats_empty_conversation(manager):
    assert manager.get_conversation_stats("missing") == {
        "total_connections": 0,
        "healthy_connections": 0,
        "idle_connections": 0,
    }


def test_stats_all_healthy_connections(manager):
    first = FakeWebSocket()
    second = FakeWebSocket()
    manager.add_connection("conversation-1", first)
    manager.add_connection("conversation-1", second)

    stats = manager.get_conversation_stats("conversation-1")

    assert stats == {
        "total_connections": 2,
        "healthy_connections": 2,
        "idle_connections": 0,
    }


def test_stats_all_idle_connections(manager):
    websocket = FakeWebSocket()
    manager.add_connection("conversation-1", websocket)
    old_time = datetime.now(timezone.utc) - timedelta(seconds=301)
    manager._metadata[websocket]["last_activity"] = old_time

    with patch("app.services.connection_manager.settings.WEBSOCKET_IDLE_THRESHOLD_SECONDS", 300):
        stats = manager.get_conversation_stats("conversation-1")

    assert stats["total_connections"] == 1
    assert stats["healthy_connections"] == 0
    assert stats["idle_connections"] == 1


def test_stats_mixed_healthy_and_idle_connections(manager):
    healthy = FakeWebSocket()
    idle = FakeWebSocket()
    manager.add_connection("conversation-1", healthy)
    manager.add_connection("conversation-1", idle)
    manager._metadata[idle]["last_activity"] = datetime.now(timezone.utc) - timedelta(seconds=301)

    with patch("app.services.connection_manager.settings.WEBSOCKET_IDLE_THRESHOLD_SECONDS", 300):
        stats = manager.get_conversation_stats("conversation-1")

    assert stats == {
        "total_connections": 2,
        "healthy_connections": 1,
        "idle_connections": 1,
    }


def test_stats_marks_exact_threshold_as_idle(manager):
    websocket = FakeWebSocket()
    fixed_now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    manager.add_connection("conversation-1", websocket)
    manager._metadata[websocket]["last_activity"] = fixed_now - timedelta(seconds=300)

    with patch("app.services.connection_manager.datetime") as datetime_mock:
        datetime_mock.now.return_value = fixed_now
        with patch("app.services.connection_manager.settings.WEBSOCKET_IDLE_THRESHOLD_SECONDS", 300):
            stats = manager.get_conversation_stats("conversation-1")

    assert stats["idle_connections"] == 1
    assert stats["healthy_connections"] == 0


def test_broadcast_sends_payload_to_healthy_connections(manager):
    first = FakeWebSocket()
    second = FakeWebSocket()
    manager.add_connection("conversation-1", first)
    manager.add_connection("conversation-1", second)
    payload = {"type": "message", "data": {"content": "hello"}}

    asyncio.run(manager.broadcast("conversation-1", payload))

    assert first.messages == [payload]
    assert second.messages == [payload]


def test_broadcast_empty_conversation_is_safe(manager):
    asyncio.run(manager.broadcast("missing", {"type": "message", "data": {}}))

    assert manager.get_connections("missing") == []


def test_broadcast_removes_failed_client_and_preserves_metadata(manager):
    healthy = FakeWebSocket()
    failed = FakeWebSocket(error=RuntimeError("send failed"))
    manager.add_connection("conversation-1", healthy, "user-1")
    manager.add_connection("conversation-1", failed, "user-2")

    asyncio.run(manager.broadcast("conversation-1", {"type": "message", "data": {}}))

    assert manager.get_connections("conversation-1") == [healthy]
    assert healthy in manager._metadata
    assert failed not in manager._metadata


def test_broadcast_removes_disconnected_client(manager):
    healthy = FakeWebSocket()
    disconnected = FakeWebSocket(state=WebSocketState.DISCONNECTED)
    manager.add_connection("conversation-1", healthy)
    manager.add_connection("conversation-1", disconnected)

    asyncio.run(manager.broadcast("conversation-1", {"type": "message", "data": {}}))

    assert manager.get_connections("conversation-1") == [healthy]
    assert disconnected not in manager._metadata
    assert healthy.messages == [{"type": "message", "data": {}}]


def test_broadcast_runs_clients_concurrently(manager):
    started = asyncio.Event()
    release = asyncio.Event()
    slow = FakeWebSocket(started=started, release=release)
    healthy = FakeWebSocket()
    manager.add_connection("conversation-1", slow)
    manager.add_connection("conversation-1", healthy)
    payload = {"type": "message", "data": {"content": "concurrent"}}

    async def run_broadcast():
        task = asyncio.create_task(manager.broadcast("conversation-1", payload))
        await asyncio.wait_for(started.wait(), timeout=1)
        await asyncio.sleep(0)
        assert healthy.messages == [payload]
        release.set()
        await asyncio.wait_for(task, timeout=1)

    asyncio.run(run_broadcast())


def test_broadcast_keeps_healthy_clients_when_one_fails(manager):
    failed = FakeWebSocket(error=RuntimeError("send failed"))
    healthy = FakeWebSocket()
    manager.add_connection("conversation-1", failed)
    manager.add_connection("conversation-1", healthy)
    payload = {"type": "message", "data": {"content": "isolated"}}

    asyncio.run(manager.broadcast("conversation-1", payload))

    assert healthy.messages == [payload]
    assert manager.get_connections("conversation-1") == [healthy]


def test_clear_all_removes_connections_and_metadata(manager):
    first = FakeWebSocket()
    second = FakeWebSocket()
    manager.add_connection("conversation-1", first)
    manager.add_connection("conversation-2", second)

    manager.clear_all()

    assert manager._connections == {}
    assert manager._metadata == {}
    assert manager.get_connections("conversation-1") == []
    assert manager.get_connections("conversation-2") == []
