"""Mount Streamable HTTP MCP on the FastAPI application."""

from __future__ import annotations

import logging
from contextlib import AbstractAsyncContextManager
from typing import Any

from fastapi import FastAPI
from mcp.server.fastmcp.server import StreamableHTTPASGIApp

from ..config import Settings
from ..orchestrator import Orchestrator
from .auth import wrap_mcp_app
from .backends.orchestrator import OrchestratorBackend
from .server import create_mcp_server

log = logging.getLogger("mcp.mount")


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
    app.mount(path, handler)
    app.state.mcp_server = mcp
    log.info("MCP Streamable HTTP mounted at %s", path)
    return inner.router.lifespan_context(inner)
