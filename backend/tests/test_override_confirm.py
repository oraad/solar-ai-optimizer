"""REST kill switch requires confirm=true."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import router
from app.models import SystemStatus, utcnow
from tests.conftest_auth import api_with_router, clear_auth_env


@pytest.fixture
def client(monkeypatch):
    clear_auth_env(monkeypatch)
    orch = MagicMock()
    orch.apply_override = AsyncMock(return_value={"kill_switch": True})
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
    tc = api_with_router(router, orch)
    return tc, orch


def test_kill_switch_without_confirm_rejected(client):
    tc, orch = client
    res = tc.post("/api/override", json={"kill_switch": True})
    assert res.status_code == 400
    assert "confirm" in res.json()["detail"].lower()
    orch.apply_override.assert_not_awaited()


def test_kill_switch_with_confirm_accepted(client):
    tc, orch = client
    res = tc.post("/api/override", json={"kill_switch": True, "confirm": True})
    assert res.status_code == 200
    orch.apply_override.assert_awaited_once()


@pytest.fixture
def viewer_client(monkeypatch):
    clear_auth_env(monkeypatch)
    monkeypatch.setenv("TRUST_INGRESS_HEADERS", "true")
    monkeypatch.setenv("TRUSTED_PROXY_IPS", "127.0.0.1")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("HA_TOKEN", "")
    monkeypatch.setenv("HA_BASE_URL", "http://127.0.0.1:9")
    from app.config import get_settings

    get_settings.cache_clear()

    orch = MagicMock()
    orch.apply_override = AsyncMock(return_value={"kill_switch": True})
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
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api.auth import AuthGateMiddleware, UserContextMiddleware

    app = FastAPI()
    app.state.orchestrator = orch
    resolver = AsyncMock()
    resolver.is_admin = AsyncMock(return_value=False)
    app.state.admin_resolver = resolver
    app.add_middleware(AuthGateMiddleware)
    app.add_middleware(UserContextMiddleware)
    app.include_router(router)
    return TestClient(app, client=("127.0.0.1", 12345)), orch


def test_viewer_kill_switch_with_confirm(viewer_client):
    tc, orch = viewer_client
    res = tc.post(
        "/api/override",
        json={"kill_switch": True, "confirm": True},
        headers={"X-Remote-User-Id": "viewer-1"},
    )
    assert res.status_code == 200
    orch.apply_override.assert_awaited_once()
