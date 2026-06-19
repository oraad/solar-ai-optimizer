"""Optional API token auth for standalone deployments."""

from __future__ import annotations

import secrets

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

# Unauthenticated liveness probe for Docker/HA healthchecks.
PUBLIC_PATHS = {"/api/health"}


class ApiTokenMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, token: str) -> None:  # noqa: ANN001
        super().__init__(app)
        self._token = token
        self._expected = f"Bearer {token}"

    def _authorized(self, request: Request) -> bool:
        auth = request.headers.get("Authorization", "")
        if len(auth) != len(self._expected):
            return False
        return secrets.compare_digest(auth, self._expected)

    async def dispatch(self, request: Request, call_next):  # noqa: ANN001
        if not self._token:
            return await call_next(request)
        path = request.url.path
        if path in PUBLIC_PATHS:
            return await call_next(request)
        if path.startswith("/api") or path == "/metrics":
            if not self._authorized(request):
                return JSONResponse({"detail": "Unauthorized"}, status_code=401)
        return await call_next(request)
