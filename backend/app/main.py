import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.config import settings
from app.db import db
from app.routes.auth import router as auth_router
from app.routes.conversations import router as conversations_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Application startup complete app=%s version=%s", settings.APP_NAME, settings.APP_VERSION)
    yield
    logger.info("Application shutdown initiated app=%s", settings.APP_NAME)
    db.close_client()
    logger.info("Application shutdown complete app=%s", settings.APP_NAME)


app = FastAPI(title=settings.APP_NAME, version=settings.APP_VERSION, lifespan=lifespan)
app.include_router(auth_router)
app.include_router(conversations_router)


@app.get("/health")
def health_check():
    mongo_status = db.health_check()

    return {
        "status": "ok",
        "message": "FastAPI application is running.",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "database": mongo_status,
        "database_status": "connected" if mongo_status.get("connected") else "unavailable",
    }


@app.get("/ready")
def ready_check():
    readiness = db.get_readiness_status()
    ready = bool(readiness.get("ready"))
    payload = {
        "status": "ok" if ready else "not_ready",
        "ready": ready,
        "database": readiness.get("database", settings.MONGODB_DB),
    }
    if readiness.get("indexes") is not None:
        payload["indexes"] = readiness["indexes"]

    status_code = 200 if ready else 503
    return JSONResponse(status_code=status_code, content=payload)


@app.get("/")
def root():
    return {"message": f"{settings.APP_NAME} is running"}
