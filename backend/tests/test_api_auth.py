"""API auth middleware: ingress bypass and bearer token."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.auth import AuthGateMiddleware, UserContextMiddleware
from app.api.metrics import metrics_router
from app.api.routes import router
from app.models import SystemStatus, utcnow
from tests.conftest import wire_orchestrator_site_tz


@pytest.fixture
def authed_client(monkeypatch):
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
    wire_orchestrator_site_tz(orch)
    monkeypatch.setenv("API_TOKEN", "secret-token")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("HA_TOKEN", "")
    monkeypatch.setenv("HA_BASE_URL", "http://127.0.0.1:9")

    from app.config import get_settings

    get_settings.cache_clear()

    app = FastAPI()
    app.state.orchestrator = orch
    app.state.admin_resolver = AsyncMock()
    app.add_middleware(AuthGateMiddleware)
    app.add_middleware(UserContextMiddleware)
    app.include_router(metrics_router)
    app.include_router(router)
    return TestClient(app)


def test_health_public_without_token(authed_client):
    res = authed_client.get("/api/health")
    assert res.status_code == 200


def test_status_requires_token(authed_client):
    res = authed_client.get("/api/status")
    assert res.status_code == 401


def test_status_with_bearer_token(authed_client):
    res = authed_client.get(
        "/api/status",
        headers={"Authorization": "Bearer secret-token"},
    )
    assert res.status_code == 200


def test_ingress_bypasses_token(authed_client, monkeypatch):
    monkeypatch.setenv("TRUST_INGRESS_HEADERS", "true")
    from app.config import get_settings

    get_settings.cache_clear()
    res = authed_client.get(
        "/api/status",
        headers={"X-Remote-User-Id": "ha-user"},
    )
    assert res.status_code == 200


def test_metrics_requires_token(authed_client):
    res = authed_client.get("/metrics")
    assert res.status_code == 401
