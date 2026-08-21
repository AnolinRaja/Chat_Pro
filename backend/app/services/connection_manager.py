from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from fastapi.encoders import jsonable_encoder
from starlette.websockets import WebSocket, WebSocketState

from app.config import settings


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[str, list[WebSocket]] = defaultdict(list)
        self._metadata: dict[WebSocket, dict[str, Any]] = {}

    def add_connection(self, conversation_id: str, websocket: WebSocket, user_id: str | None = None) -> None:
        conversation_connections = self._connections.setdefault(conversation_id, [])
        if websocket not in conversation_connections:
            conversation_connections.append(websocket)
        now = datetime.now(timezone.utc)
        self._metadata[websocket] = {
            "conversation_id": conversation_id,
            "user_id": user_id,
            "connected_at": now,
            "last_activity": now,
        }

    def update_activity(self, websocket: WebSocket) -> None:
        if websocket in self._metadata:
            self._metadata[websocket]["last_activity"] = datetime.now(timezone.utc)

    def remove_connection(self, conversation_id: str, websocket: WebSocket) -> None:
        conversation_connections = self._connections.get(conversation_id)
        if conversation_connections is None:
            return

        self._connections[conversation_id] = [ws for ws in conversation_connections if ws is not websocket]
        if not self._connections[conversation_id]:
            self._connections.pop(conversation_id, None)
        if websocket in self._metadata:
            del self._metadata[websocket]

    def get_connections(self, conversation_id: str) -> list[WebSocket]:
        return list(self._connections.get(conversation_id, []))

    def get_conversation_stats(self, conversation_id: str) -> dict[str, int]:
        connections = self.get_connections(conversation_id)
        now = datetime.now(timezone.utc)
        idle_threshold = settings.WEBSOCKET_IDLE_THRESHOLD_SECONDS
        healthy_count = 0
        idle_count = 0
        for ws in connections:
            if ws in self._metadata:
                last_activity = self._metadata[ws]["last_activity"]
                time_since_activity = (now - last_activity).total_seconds()
                if time_since_activity >= idle_threshold:
                    idle_count += 1
                else:
                    healthy_count += 1
            else:
                healthy_count += 1
        return {
            "total_connections": len(connections),
            "healthy_connections": healthy_count,
            "idle_connections": idle_count,
        }

    async def broadcast(self, conversation_id: str, message: dict[str, Any]) -> None:
        payload = jsonable_encoder(message)
        await asyncio.gather(
            *(self._send_to_connection(conversation_id, websocket, payload)
              for websocket in self.get_connections(conversation_id))
        )

    async def _send_to_connection(
        self,
        conversation_id: str,
        websocket: WebSocket,
        payload: Any,
    ) -> None:
        try:
            if websocket.application_state == WebSocketState.CONNECTED:
                await websocket.send_json(payload)
            else:
                self.remove_connection(conversation_id, websocket)
        except Exception:
            self.remove_connection(conversation_id, websocket)

    def clear_all(self) -> None:
        self._connections.clear()
        self._metadata.clear()

    @staticmethod
    def _is_stale(websocket: WebSocket) -> bool:
        application_state = getattr(websocket, "application_state", None)
        if application_state is None:
            return False
        return application_state == WebSocketState.DISCONNECTED


connection_manager = ConnectionManager()
