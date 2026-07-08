"""Mount Streamable HTTP MCP on the FastAPI application."""

from __future__ import annotations

import logging

from fastapi import FastAPI

from ..config import Settings
from ..orchestrator import Orchestrator
from .auth import wrap_mcp_app
from .backends.orchestrator import OrchestratorBackend
from .server import create_mcp_server

log = logging.getLogger("mcp.mount")


def mount_mcp_http(app: FastAPI, orchestrator: Orchestrator, settings: Settings) -> None:
    """Attach MCP Streamable HTTP when enabled and auth is configured."""
    if not settings.mcp_enabled:
        return

    if not settings.is_addon and not settings.mcp_auth_configured:
        log.error(
            "MCP_ENABLED=true but no MCP_TOKEN or API_TOKEN set — refusing to mount /mcp"
        )
        return

    backend = OrchestratorBackend(orchestrator, rate_limit_key="http-mcp")
    mcp = create_mcp_server(lambda: backend, transport="http")
    path = settings.mcp_http_path.rstrip("/") or "/mcp"
    mcp_app = wrap_mcp_app(mcp.streamable_http_app(), settings)
    app.mount(path, mcp_app)
    app.state.mcp_server = mcp
    log.info("MCP Streamable HTTP mounted at %s", path)
