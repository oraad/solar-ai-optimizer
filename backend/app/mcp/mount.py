"""Mount Streamable HTTP MCP on the FastAPI application."""

from __future__ import annotations

import logging
from contextlib import AbstractAsyncContextManager
from typing import Any

from fastapi import FastAPI
from mcp.server.fastmcp.server import StreamableHTTPASGIApp
from starlette.routing import Match, Mount
from starlette.types import Scope

from ..config import Settings
from ..orchestrator import Orchestrator
from .auth import wrap_mcp_app
from .backends.orchestrator import OrchestratorBackend
from .server import create_mcp_server

log = logging.getLogger("mcp.mount")


class ExactPathMount(Mount):
    """Like Mount, but also matches the exact base path (no trailing slash).

    Starlette ``Mount("/mcp")`` only matches ``/mcp/...`` (regex requires a
    slash after the prefix). Without this, bare ``POST /mcp`` falls through to
    the static UI mount at ``/`` and returns 405.
    """

    def matches(self, scope: Scope) -> tuple[Match, Scope]:
        if scope["type"] in ("http", "websocket"):
            from starlette.routing import get_route_path

            route_path = get_route_path(scope)
            if route_path == self.path:
                root_path = scope.get("root_path", "")
                return Match.FULL, {
                    "path_params": dict(scope.get("path_params", {})),
                    "app_root_path": scope.get("app_root_path", root_path),
                    "root_path": root_path + self.path,
                    "path": "/",
                    "endpoint": self.app,
                }
        return super().matches(scope)


def mount_mcp_http(
    app: FastAPI, orchestrator: Orchestrator, settings: Settings
) -> AbstractAsyncContextManager[Any] | None:
    """Attach MCP Streamable HTTP when enabled and auth is configured.

    Returns the MCP Starlette lifespan context manager (session manager), or
    None when MCP is not mounted. Callers must enter the lifespan while the
    app is running — FastAPI does not start mounted-subapp lifespans.

    The StreamableHTTP ASGI handler is mounted directly (not the nested Starlette
    app with default path ``/mcp``) so the public URL is ``{mcp_http_path}``
    rather than ``{mcp_http_path}/mcp``.
    """
    if not settings.mcp_enabled:
        return None

    if not settings.mcp_auth_configured:
        log.error(
            "MCP_ENABLED=true but no MCP_TOKEN or API_TOKEN set — refusing to mount /mcp"
        )
        return None

    backend = OrchestratorBackend(orchestrator, rate_limit_key="http-mcp")
    mcp = create_mcp_server(lambda: backend, transport="http")
    path = settings.mcp_http_path.rstrip("/") or "/mcp"
    # Builds the session manager and a Starlette lifespan we must enter below.
    inner = mcp.streamable_http_app()
    handler = wrap_mcp_app(StreamableHTTPASGIApp(mcp.session_manager), settings)
    # Prefer router.routes so ExactPathMount is used (app.mount always builds Mount).
    app.router.routes.append(ExactPathMount(path, app=handler, name="mcp"))
    app.state.mcp_server = mcp
    log.info("MCP Streamable HTTP mounted at %s", path)
    return inner.router.lifespan_context(inner)
