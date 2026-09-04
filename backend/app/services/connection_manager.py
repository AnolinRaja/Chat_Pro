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
        existing_metadata = self._metadata.get(websocket)
        if existing_metadata is not None and existing_metadata["conversation_id"] != conversation_id:
            raise ValueError(
                "WebSocket is already registered to a different conversation."
            )

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

    def try_add_connection(
        self,
        conversation_id: str,
        websocket: WebSocket,
        user_id: str,
        max_connections: int,
    ) -> bool:
        if self.get_user_connection_count(user_id) >= max_connections:
            return False
        self.add_connection(conversation_id, websocket, user_id)
        return True

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

    def get_user_connection_count(self, user_id: str) -> int:
        return sum(
            metadata.get("user_id") == user_id
            for metadata in self._metadata.values()
        )

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

    def get_connections_for_conversation_or_participants(
        self,
        conversation_id: str,
        participant_user_ids: list[str] | None = None,
    ) -> list[WebSocket]:
        result: list[WebSocket] = []
        direct_connections = self._connections.get(conversation_id, [])
        for ws in direct_connections:
            if ws not in result:
                result.append(ws)

        if not participant_user_ids:
            return result

        participant_set = set(participant_user_ids)
        for ws, meta in list(self._metadata.items()):
            if meta.get("user_id") in participant_set:
                if ws not in result:
                    result.append(ws)

        return result

    async def broadcast(
        self,
        conversation_id: str,
        message: dict[str, Any],
        participant_user_ids: list[str] | None = None,
    ) -> None:
        payload = jsonable_encoder(message)
        connections = self.get_connections_for_conversation_or_participants(conversation_id, participant_user_ids)
        await asyncio.gather(
            *(self._send_to_connection(websocket, payload)
              for websocket in connections)
        )

    async def _send_to_connection(
        self,
        websocket: WebSocket,
        payload: Any,
    ) -> None:
        metadata = self._metadata.get(websocket)
        if metadata is None:
            return

        if websocket.application_state != WebSocketState.CONNECTED:
            self._remove_connection_safely(metadata.get("conversation_id", ""), websocket)
            return

        try:
            await websocket.send_json(payload)
        except Exception:
            self._remove_connection_safely(metadata.get("conversation_id", ""), websocket)

    def _remove_connection_safely(self, conversation_id: str, websocket: WebSocket) -> None:
        metadata = self._metadata.get(websocket)
        if metadata is not None and metadata.get("conversation_id") != conversation_id:
            self._remove_from_conversation(conversation_id, websocket)
            return

        try:
            self.remove_connection(conversation_id, websocket)
        except Exception:
            self._remove_from_conversation(conversation_id, websocket)
            if self._metadata.get(websocket) is metadata:
                self._metadata.pop(websocket, None)

    def _remove_from_conversation(self, conversation_id: str, websocket: WebSocket) -> None:
        conversation_connections = self._connections.get(conversation_id)
        if conversation_connections is None:
            return

        remaining_connections = [
            ws for ws in conversation_connections if ws is not websocket
        ]
        if remaining_connections:
            self._connections[conversation_id] = remaining_connections
        else:
            self._connections.pop(conversation_id, None)

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
