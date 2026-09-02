import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.db import db
from app.routes.admin_audit import router as admin_audit_router
from app.routes.admin_auth import router as admin_auth_router
from app.routes.admin_organizations import router as admin_organizations_router
from app.routes.admin_requests import router as admin_requests_router
from app.routes.auth import router as auth_router
from app.routes.conversations import router as conversations_router
from app.routes.organizations import direct_router as direct_organizations_router, router as organizations_router
from app.routes.users import router as users_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Application startup complete app=%s version=%s", settings.APP_NAME, settings.APP_VERSION)
    yield
    logger.info("Application shutdown initiated app=%s", settings.APP_NAME)
    db.close_client()
    logger.info("Application shutdown complete app=%s", settings.APP_NAME)


app = FastAPI(title=settings.APP_NAME, version=settings.APP_VERSION, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://chat-pro-ebon.vercel.app",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_observability_middleware(request: Request, call_next):
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    start = time.perf_counter()

    try:
        response = await call_next(request)
    except Exception:
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        logger.error(
            "HTTP request failed method=%s path=%s status=%s duration_ms=%s request_id=%s",
            request.method,
            request.url.path,
            500,
            duration_ms,
            request_id,
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal Server Error"},
            headers={"X-Request-ID": request_id},
        )

    duration_ms = round((time.perf_counter() - start) * 1000, 2)
    response.headers["X-Request-ID"] = request_id
    logger.info(
        "HTTP request completed method=%s path=%s status=%s duration_ms=%s request_id=%s",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
        request_id,
    )
    return response


app.include_router(admin_audit_router)
app.include_router(admin_auth_router)
app.include_router(admin_organizations_router)
app.include_router(admin_requests_router)
app.include_router(auth_router)
app.include_router(organizations_router)
app.include_router(direct_organizations_router)
app.include_router(conversations_router)
app.include_router(users_router)


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
