"""GET /api/me for ingress, token, and open modes."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.auth import AuthGateMiddleware, UserContextMiddleware
from app.api.routes import router
from app.models import SystemStatus, utcnow


@pytest.fixture
def me_client(monkeypatch):
    orch = MagicMock()
    orch.build_status.return_value = SystemStatus(
        ha_connected=True,
        telemetry_stale=False,
        telemetry_age_seconds=1.0,
        forecast_misconfigured=False,
        forecast_degraded=False,
        engine_mode="rules",
        engine_active="rules",
        shadow_mode=True,
        paused=False,
        last_updated=utcnow(),
    )
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("HA_TOKEN", "")
    monkeypatch.setenv("HA_BASE_URL", "http://127.0.0.1:9")

    from app.config import get_settings

    get_settings.cache_clear()

    app = FastAPI()
    app.state.orchestrator = orch
    resolver = AsyncMock()
    resolver.is_admin = AsyncMock(return_value=True)
    app.state.admin_resolver = resolver
    app.add_middleware(AuthGateMiddleware)
    app.add_middleware(UserContextMiddleware)
    app.include_router(router)
    return TestClient(app)


def test_me_open_mode(me_client, monkeypatch):
    monkeypatch.delenv("API_TOKEN", raising=False)
    monkeypatch.delenv("LOCAL_ADMIN_PASSWORD", raising=False)
    monkeypatch.delenv("LOCAL_ADMIN_PASSWORD_HASH", raising=False)
    from app.config import get_settings

    get_settings.cache_clear()
    res = me_client.get("/api/me")
    assert res.status_code == 200
    assert res.json()["auth_mode"] == "open"
    assert res.json()["is_admin"] is True


def test_me_ingress_mode(me_client, monkeypatch):
    monkeypatch.setenv("TRUST_INGRESS_HEADERS", "true")
    from app.config import get_settings

    get_settings.cache_clear()
    res = me_client.get(
        "/api/me",
        headers={
            "X-Remote-User-Id": "ha-1",
            "X-Remote-User-Name": "viewer",
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["auth_mode"] == "ingress"
    assert body["username"] == "viewer"


def test_me_token_mode(me_client, monkeypatch):
    monkeypatch.setenv("API_TOKEN", "secret")
    from app.config import get_settings

    get_settings.cache_clear()
    res = me_client.get("/api/me", headers={"Authorization": "Bearer secret"})
    assert res.status_code == 200
    assert res.json()["auth_mode"] == "token"
