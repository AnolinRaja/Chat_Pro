import asyncio

import pytest
from starlette.websockets import WebSocketState

from app.services.connection_manager import ConnectionManager


class FakeWebSocket:
    def __init__(self, *, state=WebSocketState.CONNECTED, error=None, disconnect_before_send=False):
        self.application_state = state
        self.error = error
        self.disconnect_before_send = disconnect_before_send
        self.messages = []

    async def send_json(self, payload):
        if self.disconnect_before_send:
            self.application_state = WebSocketState.DISCONNECTED
            raise RuntimeError("connection closed during send")
        if self.error is not None:
            raise self.error
        self.messages.append(payload)


@pytest.fixture
def manager():
    return ConnectionManager()


def test_broadcast_cleans_connection_disconnected_during_send(manager):
    stale = FakeWebSocket(disconnect_before_send=True)
    healthy = FakeWebSocket()
    manager.add_connection("conversation-1", stale, "user-stale")
    manager.add_connection("conversation-1", healthy, "user-healthy")
    payload = {"type": "message", "data": {"content": "hello"}}

    asyncio.run(manager.broadcast("conversation-1", payload))

    assert healthy.messages == [payload]
    assert manager.get_connections("conversation-1") == [healthy]
    assert stale not in manager._metadata


def test_broadcast_cleans_client_when_send_fails(manager):
    failed = FakeWebSocket(error=RuntimeError("send failed"))
    healthy = FakeWebSocket()
    manager.add_connection("conversation-1", failed, "user-failed")
    manager.add_connection("conversation-1", healthy, "user-healthy")

    asyncio.run(manager.broadcast("conversation-1", {"type": "message", "data": {}}))

    assert healthy.messages == [{"type": "message", "data": {}}]
    assert failed not in manager.get_connections("conversation-1")
    assert failed not in manager._metadata
    assert healthy in manager._metadata


def test_broadcast_skips_snapshot_connection_already_removed(manager):
    websocket = FakeWebSocket()
    manager.add_connection("conversation-1", websocket)
    snapshot = manager.get_connections("conversation-1")
    manager.remove_connection("conversation-1", websocket)

    asyncio.run(manager._send_to_connection("conversation-1", snapshot[0], {"type": "message", "data": {}}))

    assert websocket.messages == []
    assert manager.get_connections("conversation-1") == []
    assert manager._metadata == {}


def test_broadcast_cleans_connection_with_missing_metadata(manager):
    websocket = FakeWebSocket()
    healthy = FakeWebSocket()
    manager.add_connection("conversation-1", websocket)
    manager.add_connection("conversation-1", healthy)
    manager._metadata.pop(websocket)

    asyncio.run(manager.broadcast("conversation-1", {"type": "message", "data": {}}))

    assert websocket not in manager.get_connections("conversation-1")
    assert healthy.messages == [{"type": "message", "data": {}}]
    assert healthy in manager._metadata


def test_broadcast_does_not_remove_metadata_owned_by_another_conversation(manager):
    websocket = FakeWebSocket()
    manager.add_connection("conversation-2", websocket, "user-2")
    manager._connections["conversation-1"].append(websocket)

    asyncio.run(manager.broadcast("conversation-1", {"type": "message", "data": {}}))

    assert websocket not in manager.get_connections("conversation-1")
    assert manager.get_connections("conversation-2") == [websocket]
    assert manager._metadata[websocket]["conversation_id"] == "conversation-2"


def test_cleanup_failure_does_not_break_healthy_delivery(manager):
    failed = FakeWebSocket(error=RuntimeError("send failed"))
    healthy = FakeWebSocket()
    manager.add_connection("conversation-1", failed)
    manager.add_connection("conversation-1", healthy)

    def fail_cleanup(*args, **kwargs):
        raise RuntimeError("cleanup failed")

    manager.remove_connection = fail_cleanup
    payload = {"type": "message", "data": {"content": "still delivered"}}

    asyncio.run(manager.broadcast("conversation-1", payload))

    assert healthy.messages == [payload]
    assert manager.get_connections("conversation-1") == [healthy]
    assert failed not in manager._metadata
    assert healthy in manager._metadata


def test_failed_connection_cleanup_does_not_corrupt_other_conversation(manager):
    failed = FakeWebSocket(error=RuntimeError("send failed"))
    other = FakeWebSocket()
    manager.add_connection("conversation-1", failed, "user-failed")
    manager.add_connection("conversation-2", other, "user-other")

    asyncio.run(manager.broadcast("conversation-1", {"type": "message", "data": {}}))

    assert manager.get_connections("conversation-1") == []
    assert manager.get_connections("conversation-2") == [other]
    assert failed not in manager._metadata
    assert manager._metadata[other]["conversation_id"] == "conversation-2"


def test_broadcast_remains_concurrent_with_slow_client(manager):
    started = asyncio.Event()
    release = asyncio.Event()

    class SlowWebSocket(FakeWebSocket):
        async def send_json(self, payload):
            started.set()
            await release.wait()
            self.messages.append(payload)

    slow = SlowWebSocket()
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
    assert slow.messages == [payload]
