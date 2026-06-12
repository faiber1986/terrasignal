"""FastAPI application entrypoint: assembles routers under /api/v1, binds a
request_id to every request/log line, and warms the model service at startup.

The app boots even if the database or approved models are unavailable — startup
model loading is best-effort so /health and the OpenAPI contract are always
serveable (CI generates the frontend's TypeScript types from that contract).
Model-backed routes fail loudly only when actually invoked without a model.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from terrasignal.backend.app.logging_config import configure_logging
from terrasignal.backend.app.models_service import model_service
from terrasignal.backend.app.routers import (
    auth,
    feedback,
    forecasts,
    governance,
    portfolio,
    risk,
)

log = structlog.get_logger(__name__)

API_PREFIX = "/api/v1"

# Local Next.js dev server. Any localhost port is allowed (the dev server hops
# ports when one is busy); production swaps this for an exact allowlist. Auth is
# a bearer header, not a cookie, but we keep credentials on for parity (§8).
ALLOWED_ORIGIN_REGEX = r"http://(localhost|127\.0\.0\.1):\d+"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    try:
        model_service.load()
    except Exception as exc:  # noqa: BLE001 — boot must survive a cold DB/registry
        log.warning("model_service_load_failed", error=str(exc))
    yield


app = FastAPI(
    title="TerraSignal API",
    version="0.1.0",
    description="CRE rent forecasting & tenant default-risk platform.",
    lifespan=lifespan,
    openapi_url=f"{API_PREFIX}/openapi.json",
    docs_url=f"{API_PREFIX}/docs",
)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=ALLOWED_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)


@app.middleware("http")
async def request_context(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Assign a request_id (honoring an inbound X-Request-ID), expose it on
    request.state for audit writes, bind it to every log line, and echo it back
    on the response header so a UI action can be traced to its audit events."""
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.request_id = request_id
    structlog.contextvars.bind_contextvars(request_id=request_id)
    try:
        response = await call_next(request)
    finally:
        structlog.contextvars.clear_contextvars()
    response.headers["X-Request-ID"] = request_id
    return response


@app.get("/health", tags=["meta"])
async def health() -> dict[str, object]:
    """Unauthenticated liveness probe. `models_ready` reflects whether approved
    models were loaded — false is a valid booted state (DB still warming)."""
    return {"status": "ok", "models_ready": getattr(model_service, "ready", False)}


for _router in (
    auth.router,
    risk.router,
    forecasts.router,
    feedback.router,
    portfolio.router,
    governance.router,
):
    app.include_router(_router, prefix=API_PREFIX)
