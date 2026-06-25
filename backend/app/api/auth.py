"""Authentication middleware: session resolution and access gate."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ..config import get_settings
from ..i18n import t
from .session import (
    ANONYMOUS,
    get_session,
    is_public_api_path,
    requires_auth_gate,
    resolve_session,
)


class UserContextMiddleware(BaseHTTPMiddleware):
    """Attach resolved session to every HTTP request and WebSocket upgrade."""

    async def dispatch(self, request: Request, call_next) -> Response:  # noqa: ANN001
        settings = get_settings()
        resolver = getattr(request.app.state, "admin_resolver", None)
        session = await resolve_session(request, settings, resolver)
        request.state.session = session
        return await call_next(request)


class AuthGateMiddleware(BaseHTTPMiddleware):
    """Return 401 when local auth is enabled and the caller is unauthenticated."""

    async def dispatch(self, request: Request, call_next) -> Response:  # noqa: ANN001
        settings = get_settings()
        path = request.url.path
        if not requires_auth_gate(path, settings):
            return await call_next(request)

        session = get_session(request)
        if session.authenticated:
            return await call_next(request)

        return JSONResponse({"detail": t("api.auth.unauthorized")}, status_code=401)
