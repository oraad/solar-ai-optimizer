"""Bearer auth ASGI middleware for Streamable HTTP MCP."""

from __future__ import annotations

import json
from typing import Callable

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from ..config import Settings, get_settings
from ..observability.metrics import metrics


class McpBearerAuthMiddleware:
    """Require Bearer token on MCP HTTP transport (no cookie auth)."""

    def __init__(self, app: ASGIApp, settings: Settings | None = None) -> None:
        self.app = app
        self._settings = settings

    def _settings_for(self) -> Settings:
        return self._settings or get_settings()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        settings = self._settings_for()
        token = settings.effective_mcp_token
        if not token:
            await self._reject(send, 503, "MCP token not configured")
            return

        headers = dict(scope.get("headers") or [])
        auth = headers.get(b"authorization", b"").decode("latin-1")
        if not auth.startswith("Bearer "):
            metrics.mcp_auth_failures_total += 1
            await self._reject(send, 401, "Bearer token required")
            return
        provided = auth[7:].strip()
        if provided != token:
            metrics.mcp_auth_failures_total += 1
            await self._reject(send, 403, "Invalid bearer token")
            return

        await self.app(scope, receive, send)

    async def _reject(self, send: Send, status: int, detail: str) -> None:
        body = json.dumps({"error": detail}).encode()
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send({"type": "http.response.body", "body": body})


def wrap_mcp_app(app: ASGIApp, settings: Settings | None = None) -> ASGIApp:
    return McpBearerAuthMiddleware(app, settings=settings)
