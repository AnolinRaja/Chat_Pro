import pytest

from app.config import _get_websocket_idle_threshold_seconds, settings


@pytest.mark.parametrize("value", [1, 86400])
def test_websocket_idle_threshold_accepts_inclusive_boundaries(monkeypatch, value):
    monkeypatch.setenv("WEBSOCKET_IDLE_THRESHOLD_SECONDS", str(value))

    assert _get_websocket_idle_threshold_seconds() == value


def test_websocket_idle_threshold_defaults_to_300_seconds(monkeypatch):
    monkeypatch.delenv("WEBSOCKET_IDLE_THRESHOLD_SECONDS", raising=False)

    assert settings.WEBSOCKET_IDLE_THRESHOLD_SECONDS == 300
    assert _get_websocket_idle_threshold_seconds() == 300


@pytest.mark.parametrize("value", [0, -1])
def test_websocket_idle_threshold_rejects_values_below_one(monkeypatch, value):
    monkeypatch.setenv("WEBSOCKET_IDLE_THRESHOLD_SECONDS", str(value))

    with pytest.raises(ValueError, match="between 1 and 86400 seconds inclusive"):
        _get_websocket_idle_threshold_seconds()


def test_websocket_idle_threshold_rejects_values_above_86400(monkeypatch):
    monkeypatch.setenv("WEBSOCKET_IDLE_THRESHOLD_SECONDS", "86401")

    with pytest.raises(ValueError, match="between 1 and 86400 seconds inclusive"):
        _get_websocket_idle_threshold_seconds()
