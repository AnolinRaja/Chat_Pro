from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any

from fastapi.encoders import jsonable_encoder
from starlette.websockets import WebSocket, WebSocketState


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[str, list[WebSocket]] = defaultdict(list)

    def add_connection(self, conversation_id: str, websocket: WebSocket) -> None:
        conversation_connections = self._connections.setdefault(conversation_id, [])
        if websocket not in conversation_connections:
            conversation_connections.append(websocket)

    def remove_connection(self, conversation_id: str, websocket: WebSocket) -> None:
        conversation_connections = self._connections.get(conversation_id)
        if conversation_connections is None:
            return

        self._connections[conversation_id] = [ws for ws in conversation_connections if ws is not websocket]
        if not self._connections[conversation_id]:
            self._connections.pop(conversation_id, None)

    def get_connections(self, conversation_id: str) -> list[WebSocket]:
        return list(self._connections.get(conversation_id, []))

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

    @staticmethod
    def _is_stale(websocket: WebSocket) -> bool:
        application_state = getattr(websocket, "application_state", None)
        if application_state is None:
            return False
        return application_state == WebSocketState.DISCONNECTED


connection_manager = ConnectionManager()
