import pytest

from app.config import (
    _get_jwt_secret_key,
    _get_mongodb_uri,
    _get_websocket_idle_threshold_seconds,
    settings,
)


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


def test_jwt_secret_accepts_32_character_value(monkeypatch):
    secret = "a" * 32
    monkeypatch.setenv("JWT_SECRET_KEY", secret)

    assert _get_jwt_secret_key() == secret


def test_jwt_secret_accepts_longer_value_and_preserves_it(monkeypatch):
    secret = "a-strong-development-secret-2026-value"
    monkeypatch.setenv("JWT_SECRET_KEY", secret)

    assert _get_jwt_secret_key() == secret


@pytest.mark.parametrize("value", [None, ""])
def test_jwt_secret_rejects_missing_or_empty_value(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    else:
        monkeypatch.setenv("JWT_SECRET_KEY", value)

    with pytest.raises(ValueError, match="JWT_SECRET_KEY"):
        _get_jwt_secret_key()


def test_jwt_secret_rejects_whitespace_only_value(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", " " * 32)

    with pytest.raises(ValueError, match="JWT_SECRET_KEY"):
        _get_jwt_secret_key()


def test_jwt_secret_rejects_known_insecure_fallback(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "change-this-in-production")

    with pytest.raises(ValueError, match="insecure default"):
        _get_jwt_secret_key()


@pytest.mark.parametrize("value", ["short-secret", "b" * 31])
def test_jwt_secret_rejects_values_shorter_than_32_characters(monkeypatch, value):
    monkeypatch.setenv("JWT_SECRET_KEY", value)

    with pytest.raises(ValueError, match="at least 32 characters"):
        _get_jwt_secret_key()


def test_jwt_secret_error_does_not_expose_secret(monkeypatch):
    secret = "secret-value"
    monkeypatch.setenv("JWT_SECRET_KEY", secret)

    with pytest.raises(ValueError) as error:
        _get_jwt_secret_key()

    assert secret not in str(error.value)


@pytest.mark.parametrize(
    "name",
    [
        "WEBSOCKET_MAX_CONNECTIONS_PER_USER",
        "WEBSOCKET_MAX_MESSAGE_SIZE_BYTES",
        "WEBSOCKET_MESSAGE_RATE_LIMIT",
        "WEBSOCKET_MESSAGE_RATE_WINDOW_SECONDS",
    ],
)
def test_websocket_security_limits_accept_positive_values(monkeypatch, name):
    monkeypatch.setenv(name, "1")

    from app.config import _get_positive_int

    assert _get_positive_int(name, "5") == 1


@pytest.mark.parametrize(
    "name,value",
    [
        ("WEBSOCKET_MAX_CONNECTIONS_PER_USER", "0"),
        ("WEBSOCKET_MAX_MESSAGE_SIZE_BYTES", "-1"),
        ("WEBSOCKET_MESSAGE_RATE_LIMIT", "invalid"),
        ("WEBSOCKET_MESSAGE_RATE_WINDOW_SECONDS", "0"),
    ],
)
def test_websocket_security_limits_reject_invalid_values(monkeypatch, name, value):
    monkeypatch.setenv(name, value)

    from app.config import _get_positive_int

    with pytest.raises(ValueError, match=name):
        _get_positive_int(name, "5")


def test_explicit_secret_keeps_development_and_test_configuration_usable(monkeypatch):
    secret = "explicit-test-secret-with-32-or-more-chars"
    monkeypatch.setenv("JWT_SECRET_KEY", secret)

    assert _get_jwt_secret_key() == secret
    assert settings.JWT_SECRET_KEY


def test_mongodb_uri_accepts_valid_values(monkeypatch):
    uri = "mongodb://localhost:27017/chatpro"
    monkeypatch.setenv("MONGODB_URI", uri)

    assert _get_mongodb_uri() == uri


@pytest.mark.parametrize("value", ["", "   ", "mongodb://", "not-a-mongodb-uri", "http://localhost:27017"])
def test_mongodb_uri_rejects_invalid_values(monkeypatch, value):
    monkeypatch.setenv("MONGODB_URI", value)

    with pytest.raises(ValueError, match="MongoDB"):
        _get_mongodb_uri()
