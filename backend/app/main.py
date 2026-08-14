from fastapi import FastAPI

from app.config import settings
from app.db import db
from app.routes.auth import router as auth_router

app = FastAPI(title=settings.APP_NAME, version=settings.APP_VERSION)
app.include_router(auth_router)


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


@app.get("/")
def root():
    return {"message": f"{settings.APP_NAME} is running"}
