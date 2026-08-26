import os
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _get_websocket_idle_threshold_seconds() -> int:
    value = int(os.getenv("WEBSOCKET_IDLE_THRESHOLD_SECONDS", "300"))
    if not 1 <= value <= 86400:
        raise ValueError(
            "WEBSOCKET_IDLE_THRESHOLD_SECONDS must be between "
            f"1 and 86400 seconds inclusive; got {value}"
        )
    return value


def _get_jwt_secret_key() -> str:
    value = os.getenv("JWT_SECRET_KEY")
    if value is None or not value.strip():
        raise ValueError(
            "JWT_SECRET_KEY must be explicitly configured with a strong secret."
        )
    if value == "change-this-in-production":
        raise ValueError(
            "JWT_SECRET_KEY must not use the insecure default value."
        )
    if len(value) < 32:
        raise ValueError("JWT_SECRET_KEY must be at least 32 characters long.")
    return value


def _get_positive_int(name: str, default: str) -> int:
    try:
        value = int(os.getenv(name, default))
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a positive integer.")
    if value <= 0:
        raise ValueError(f"{name} must be a positive integer.")
    return value


def _get_mongodb_uri() -> str:
    value = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
    if value is None:
        raise ValueError("MONGODB_URI must be configured as a valid MongoDB connection string.")

    normalized = value.strip()
    if not normalized:
        raise ValueError("MONGODB_URI must be configured as a valid MongoDB connection string.")

    parsed = urlparse(normalized)
    if parsed.scheme in {"mongodb", "mongodb+srv"} and parsed.hostname:
        return normalized

    raise ValueError("MONGODB_URI must be a valid MongoDB connection string.")


class Settings:
    APP_NAME: str = os.getenv("APP_NAME", "chatpro-backend")
    APP_VERSION: str = os.getenv("APP_VERSION", "0.1.0")
    HOST: str = os.getenv("HOST", "127.0.0.1")
    PORT: int = int(os.getenv("PORT", "8000"))
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"
    MONGODB_URI: str = _get_mongodb_uri()
    MONGODB_DB: str = os.getenv("MONGODB_DB", "chatpro")
    JWT_SECRET_KEY: str = _get_jwt_secret_key()
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
    WEBSOCKET_IDLE_THRESHOLD_SECONDS: int = _get_websocket_idle_threshold_seconds()
    AUTH_RATE_LIMIT_REQUESTS: int = _get_positive_int("AUTH_RATE_LIMIT_REQUESTS", "10")
    AUTH_RATE_LIMIT_WINDOW_SECONDS: int = _get_positive_int("AUTH_RATE_LIMIT_WINDOW_SECONDS", "60")
    WEBSOCKET_MAX_CONNECTIONS_PER_USER: int = _get_positive_int(
        "WEBSOCKET_MAX_CONNECTIONS_PER_USER", "5"
    )
    WEBSOCKET_MAX_MESSAGE_SIZE_BYTES: int = _get_positive_int(
        "WEBSOCKET_MAX_MESSAGE_SIZE_BYTES", "65536"
    )
    WEBSOCKET_MESSAGE_RATE_LIMIT: int = _get_positive_int(
        "WEBSOCKET_MESSAGE_RATE_LIMIT", "30"
    )
    WEBSOCKET_MESSAGE_RATE_WINDOW_SECONDS: int = _get_positive_int(
        "WEBSOCKET_MESSAGE_RATE_WINDOW_SECONDS", "60"
    )


settings = Settings()
