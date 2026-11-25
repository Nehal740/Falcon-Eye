"""Falcon Eye API - Powerful security. Simple experience.

Start (development):  python -m uvicorn main:app --reload
Interactive docs:     http://127.0.0.1:8000/docs
"""

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from errors import AppError, error_response, register_error_handlers
from migrations import init_db
from routers import (
    agents, approvals, assistant, auth, dashboard, events, firewall, policies, verify,
    workspaces,
)

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("falcon_eye")

VERSION = "1.0.0"

DESCRIPTION = """
**Falcon Eye** is a firewall for AI agents.

* **People** sign in (`/auth`) and manage workspaces, agents, policies and approvals.
* **AI agents** call `/v1/evaluate` with their agent key and receive
  `ALLOW`, `BLOCK` or `REQUIRE_APPROVAL`.

Falcon Eye makes decisions and keeps records. It does not carry out actions.
"""

TAGS = [
    {"name": "Agent API (for your AI agents)", "description": "Called by your AI agents with an agent key."},
    {"name": "Authentication", "description": "Create an account, sign in and out."},
    {"name": "Workspaces", "description": "Workspaces, members, audit log and assistant settings."},
    {"name": "Agents", "description": "Register agents and manage their keys."},
    {"name": "Output verification", "description": "Check agent output and tool calls for injection, secrets and unsupported claims."},
    {"name": "Policies", "description": "Rules that decide what agents may do."},
    {"name": "Events", "description": "The record of every firewall decision."},
    {"name": "Approvals", "description": "Human review of sensitive actions."},
    {"name": "Dashboard", "description": "Live numbers for the dashboard."},
    {"name": "AI assistant", "description": "Help for using Falcon Eye."},
    {"name": "Health", "description": "Is the service running?"},
]


@asynccontextmanager
async def lifespan(_app: FastAPI):
    problems = settings.validate_for_production()
    if problems:
        raise RuntimeError("Unsafe production configuration: " + " ".join(problems))
    init_db()
    logger.info("Falcon Eye %s started (%s).", VERSION, settings.environment)
    yield


app = FastAPI(
    title="Falcon Eye API",
    version=VERSION,
    description=DESCRIPTION,
    openapi_tags=TAGS,
    lifespan=lifespan,
    docs_url="/docs" if settings.enable_docs else None,
    redoc_url="/redoc" if settings.enable_docs else None,
    openapi_url="/openapi.json" if settings.enable_docs else None,
)

register_error_handlers(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-Requested-With", "X-Falcon-Key"],
)


@app.middleware("http")
async def protect(request: Request, call_next):
    """Reject oversized bodies and add standard security headers."""
    length = request.headers.get("content-length")
    if length and length.isdigit() and int(length) > settings.max_body_bytes:
        return error_response(413, "too_large", "That request is too large.",
                              "Send less data and try again.")
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault("Cross-Origin-Resource-Policy", "same-site")
    if not request.url.path.startswith(("/docs", "/redoc", "/openapi")):
        response.headers.setdefault("Cache-Control", "no-store")
        # The API only returns JSON, so it needs no scripts, styles or frames at all.
        response.headers.setdefault("Content-Security-Policy",
                                    "default-src 'none'; frame-ancestors 'none'")
    if settings.is_production:
        response.headers.setdefault("Strict-Transport-Security",
                                    "max-age=31536000; includeSubDomains")
    return response


for module in (auth, workspaces, agents, policies, firewall, verify, events, approvals,
               dashboard, assistant):
    app.include_router(module.router)


@app.get("/", tags=["Health"], include_in_schema=False)
def root():
    return {"name": "Falcon Eye API", "version": VERSION, "docs": "/docs", "health": "/health"}


@app.get("/health", tags=["Health"], summary="Is the API running?")
def health():
    return {"status": "ok", "version": VERSION}


@app.get("/health/ready", tags=["Health"], summary="Is the API ready (database reachable)?")
def ready(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        logger.exception("Readiness check failed")
        raise AppError(503, "database_unavailable", "The database is not reachable.",
                       "Check that the database is running and DATABASE_URL is correct.")
    return {"status": "ready", "database": "ok"}
