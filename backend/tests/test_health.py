import asyncio
import importlib
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.db import Database, db
from app.main import app
from app.routes.auth import _enforce_auth_rate_limit
from app.services.rate_limiter import auth_rate_limiter

conversations_module = importlib.import_module("app.routes.conversations")

client = TestClient(app)


def test_health_endpoint_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


def test_ready_endpoint_returns_200_when_database_is_ready(monkeypatch):
    monkeypatch.setattr(
        db,
        "get_readiness_status",
        lambda: {
            "ready": True,
            "connected": True,
            "database": "chatpro",
            "indexes": {"users": {"present": [], "missing": [], "misconfigured": []}},
        },
    )

    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json()["ready"] is True
    assert response.json()["status"] == "ok"


def test_ready_endpoint_returns_503_when_database_is_not_ready(monkeypatch):
    monkeypatch.setattr(
        db,
        "get_readiness_status",
        lambda: {
            "ready": False,
            "connected": False,
            "database": "chatpro",
            "indexes": {"users": {"present": [], "missing": ["unique_email_idx"], "misconfigured": []}},
        },
    )

    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json()["ready"] is False
    assert response.json()["status"] == "not_ready"


def test_ready_endpoint_does_not_expose_sensitive_fields(monkeypatch):
    monkeypatch.setattr(
        db,
        "get_readiness_status",
        lambda: {
            "ready": False,
            "connected": False,
            "database": "chatpro",
            "database_uri": "mongodb://user:secret@host/chatpro",
            "jwt_secret": "super-secret-value",
            "indexes": {"users": {"missing": ["unique_email_idx"]}},
        },
    )

    response = client.get("/ready")

    payload = response.json()
    assert "database_uri" not in payload
    assert "jwt_secret" not in payload
    assert "mongodb://user:secret@host" not in response.text
    assert "super-secret-value" not in response.text


def test_database_close_client_closes_initialized_client(monkeypatch):
    fake_client = Mock()
    monkeypatch.setattr(Database, "client", fake_client, raising=False)

    Database.close_client()

    fake_client.close.assert_called_once()


def test_database_close_client_is_safe_without_client(monkeypatch):
    monkeypatch.setattr(Database, "client", None, raising=False)

    Database.close_client()


def test_database_close_client_handles_close_error_safely(monkeypatch, caplog):
    fake_client = Mock()
    fake_client.close.side_effect = RuntimeError("shutdown error")
    monkeypatch.setattr(Database, "client", fake_client, raising=False)

    with caplog.at_level("WARNING"):
        Database.close_client()

    assert "MongoDB client shutdown failed" in caplog.text


def test_auth_rate_limit_logging_is_safe(monkeypatch, caplog):
    request = Mock()
    request.client.host = "127.0.0.1"
    monkeypatch.setattr(auth_rate_limiter, "check", lambda *args, **kwargs: 42)

    with pytest.raises(Exception):
        _enforce_auth_rate_limit(request, "login")

    assert "Authentication rate limit exceeded" in caplog.text
    assert "127.0.0.1" in caplog.text
    assert "token" not in caplog.text.lower()


def test_websocket_message_size_rejection_logs_safely(monkeypatch, caplog):
    websocket = Mock()
    websocket.query_params = {"token": "sensitive-token-value"}
    websocket.headers = {}
    websocket.accept = AsyncMock()
    websocket.close = AsyncMock()
    websocket.receive_text = AsyncMock(side_effect=["abcde", WebSocketDisconnect()])
    websocket.send_json = AsyncMock()

    monkeypatch.setattr(
        "app.routes.conversations.get_current_user_from_token",
        AsyncMock(return_value={"id": "user-123"}),
    )
    monkeypatch.setattr("app.routes.conversations.ConversationService.get_conversation", Mock(return_value={}))
    monkeypatch.setattr("app.routes.conversations.connection_manager.try_add_connection", Mock(return_value=True))
    monkeypatch.setattr("app.routes.conversations.settings.WEBSOCKET_MAX_MESSAGE_SIZE_BYTES", 4)

    with caplog.at_level("WARNING"):
        asyncio.run(conversations_module.websocket_conversation(websocket, "conversation-123"))

    assert "WebSocket message rejected" in caplog.text
    assert "sensitive-token-value" not in caplog.text
    assert "abcde" not in caplog.text
