import os
from pathlib import Path

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


class Settings:
    APP_NAME: str = os.getenv("APP_NAME", "chatpro-backend")
    APP_VERSION: str = os.getenv("APP_VERSION", "0.1.0")
    HOST: str = os.getenv("HOST", "127.0.0.1")
    PORT: int = int(os.getenv("PORT", "8000"))
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"
    MONGODB_URI: str = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
    MONGODB_DB: str = os.getenv("MONGODB_DB", "chatpro")
    JWT_SECRET_KEY: str = _get_jwt_secret_key()
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
    WEBSOCKET_IDLE_THRESHOLD_SECONDS: int = _get_websocket_idle_threshold_seconds()


settings = Settings()
