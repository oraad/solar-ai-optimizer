"""Every /api, /metrics, and /ws route must be public or guarded."""

from __future__ import annotations

from fastapi.routing import APIRoute, APIWebSocketRoute

from app.api.session import PUBLIC_API_PREFIXES, require_admin, require_authenticated
from app.main import create_app

GUARDED = {require_authenticated, require_admin}
# WebSocket auth is enforced in the handler (_ws_authorized), not via Depends.
HANDLER_AUTH_PATHS = {"/ws"}


def _dependency_calls(route) -> set:  # noqa: ANN001
    if not isinstance(route, APIRoute):
        return set()
    calls: set = set()
    stack = [route.dependant]
    while stack:
        dependant = stack.pop()
        for dep in dependant.dependencies:
            if dep.call is not None:
                calls.add(dep.call)
            if dep.dependant is not None:
                stack.append(dep.dependant)
    return calls


def test_every_api_route_is_public_or_guarded():
    app = create_app()
    for route in app.routes:
        path = getattr(route, "path", "")
        if not (path.startswith("/api") or path in ("/metrics", "/ws")):
            continue
        if path in PUBLIC_API_PREFIXES:
            continue
        if path in HANDLER_AUTH_PATHS:
            assert isinstance(route, APIWebSocketRoute), path
            continue
        deps = _dependency_calls(route)
        assert deps & GUARDED, f"{path} has no require_authenticated/require_admin dependency"
