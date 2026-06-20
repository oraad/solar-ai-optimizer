"""FastAPI application entrypoint.

Serves both the REST/WebSocket API and (when present) the built Lit dashboard,
so the whole app can run from a single container. Supports running standalone or
as a Home Assistant add-on behind ingress (via root_path).
"""

from __future__ import annotations

import logging
import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from .api import api_router, auth_router, metrics_router, ws_router
from .api.auth import AuthGateMiddleware, UserContextMiddleware
from .config import get_settings
from .config_store import ConfigStore
from .ha.users import HAAdminResolver
from .logging_setup import configure_logging, request_id_var
from .orchestrator import Orchestrator
from .scheduler import build_scheduler

log = logging.getLogger("main")

STATIC_DIR = os.environ.get("STATIC_DIR", "/app/static")


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:  # noqa: ANN001
        rid = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        token = request_id_var.set(rid)
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = rid
            return response
        finally:
            request_id_var.reset(token)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, allow_frames: bool = False) -> None:  # noqa: ANN001
        super().__init__(app)
        self._allow_frames = allow_frames

    async def dispatch(self, request: Request, call_next) -> Response:  # noqa: ANN001
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = (
            "SAMEORIGIN" if self._allow_frames else "DENY"
        )
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    fmt = "json" if settings.log_format.lower() == "json" else "text"
    configure_logging(settings.log_level, fmt=fmt)

    runtime_overrides = str(Path(settings.data_dir) / "config.runtime.yaml")
    store = ConfigStore(settings.config_path, runtime_overrides)

    log.info(
        "Starting Solar AI Optimizer (shadow_mode=%s, addon=%s, "
        "ingress_trusted=%s, local_auth=%s, api_token=%s)",
        settings.shadow_mode,
        settings.is_addon,
        settings.ingress_trusted,
        settings.local_auth_enabled,
        bool(settings.api_token),
    )
    if settings.local_admin_password and not settings.local_admin_password_hash:
        log.warning(
            "LOCAL_ADMIN_PASSWORD is set in plain text — use "
            "LOCAL_ADMIN_PASSWORD_HASH in production."
        )
    if not settings.local_auth_enabled and not settings.api_token and not settings.is_addon:
        log.warning(
            "No LOCAL_ADMIN or API_TOKEN configured — API is open on the LAN. "
            "Set LOCAL_ADMIN_PASSWORD or API_TOKEN for standalone deployments."
        )
    orchestrator = Orchestrator(settings, store)
    await orchestrator.setup()
    app.state.orchestrator = orchestrator
    admin_resolver = HAAdminResolver(settings, orchestrator.ha)
    orchestrator.set_admin_resolver(admin_resolver)
    app.state.admin_resolver = admin_resolver

    scheduler = build_scheduler(orchestrator)
    orchestrator.attach_scheduler(scheduler)
    scheduler.start()
    app.state.scheduler = scheduler
    log.info("Scheduler started.")

    try:
        yield
    finally:
        log.info("Shutting down...")
        scheduler.shutdown(wait=False)
        await orchestrator.shutdown()


def create_app() -> FastAPI:
    settings = get_settings()
    auth_locked = settings.api_token or settings.local_auth_enabled
    docs_url = None if auth_locked else "/docs"
    openapi_url = None if auth_locked else "/openapi.json"
    app = FastAPI(
        title="Solar AI Optimizer",
        version="0.1.0",
        description=(
            "Vendor-agnostic solar/battery optimizer for Home Assistant. "
            "Resilience first, then savings and self-sufficiency."
        ),
        lifespan=lifespan,
        root_path=settings.root_path or "",
        docs_url=docs_url,
        openapi_url=openapi_url,
    )
    origins = [
        o.strip()
        for o in settings.cors_origins.split(",")
        if o.strip()
    ] or ["*"]
    allow_credentials = settings.local_auth_enabled and origins != ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(SecurityHeadersMiddleware, allow_frames=settings.ingress_trusted)
    app.add_middleware(AuthGateMiddleware)
    app.add_middleware(UserContextMiddleware)
    app.include_router(auth_router)
    app.include_router(metrics_router)
    app.include_router(api_router)
    app.include_router(ws_router)

    # Serve the built dashboard if it was bundled into the image.
    static_path = Path(STATIC_DIR)
    if static_path.is_dir():
        app.mount("/", StaticFiles(directory=str(static_path), html=True), name="ui")
        log.info("Serving dashboard from %s", static_path)
    else:
        @app.get("/")
        async def root() -> dict:
            return {"name": "Solar AI Optimizer", "docs": "/docs", "api": "/api"}

    return app


app = create_app()
