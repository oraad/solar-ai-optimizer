"""Shared auth helpers for API tests."""

from __future__ import annotations

from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.auth import AuthGateMiddleware, UserContextMiddleware


def auth_headers(token: str = "test-token") -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def api_with_router(router, orchestrator) -> TestClient:
    """Minimal app with session middleware in open-auth dev mode."""
    app = FastAPI()
    app.state.orchestrator = orchestrator
    app.state.admin_resolver = AsyncMock()
    app.add_middleware(AuthGateMiddleware)
    app.add_middleware(UserContextMiddleware)
    app.include_router(router)
    return TestClient(app)


def clear_auth_env(monkeypatch) -> None:
    monkeypatch.delenv("API_TOKEN", raising=False)
    monkeypatch.delenv("LOCAL_ADMIN_PASSWORD", raising=False)
    monkeypatch.delenv("LOCAL_ADMIN_PASSWORD_HASH", raising=False)
    monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)
    from app.config import get_settings

    get_settings.cache_clear()
