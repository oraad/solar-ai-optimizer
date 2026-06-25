"""Request locale middleware."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from . import reset_locale, resolve_request_locale, set_locale


class LocaleMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:  # noqa: ANN001
        loc = resolve_request_locale(
            request.headers.get("X-Solar-Locale"),
            request.headers.get("Accept-Language"),
        )
        token = set_locale(loc)
        try:
            return await call_next(request)
        finally:
            reset_locale(token)
