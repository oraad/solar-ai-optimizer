"""Admin guard on debug forensics routes."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.auth import AuthGateMiddleware, UserContextMiddleware
from app.api.debug_routes import router as debug_router
from tests.conftest import wire_orchestrator_site_tz


@pytest.fixture
def debug_client(monkeypatch):
    orch = MagicMock()
    orch.simulate_decision.return_value = None
    orch._plan_flags.return_value = (True, True, True)
    orch.collector.latest = None
    orch.forecast.current = None
    orch.latest_grid_stats = None
    orch._telemetry_stale.return_value = True
    orch._telemetry_age_seconds.return_value = None
    orch.cfg.engine.priority_order = []
    orch.cfg.engine.mode = "rules"
    orch.cfg.engine.enabled = True
    orch.cfg.grid_charge.enabled = True
    orch.cfg.load_shedding.enabled = True
    orch._mpc = None
    orch.shadow_mode = True
    orch.paused = False
    orch.paused_shedding = False
    orch.paused_grid_charge = False
    orch.paused_optimization = False
    orch.override = MagicMock()
    orch.override.model_dump.return_value = {}
    orch.latest_decision = None
    orch.latest_results = []
    orch.latest_shed_results = []
    wire_orchestrator_site_tz(orch)
    monkeypatch.setenv("TRUST_INGRESS_HEADERS", "true")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("HA_TOKEN", "")
    monkeypatch.setenv("HA_BASE_URL", "http://127.0.0.1:9")
    from app.config import get_settings

    get_settings.cache_clear()

    app = FastAPI()
    app.state.orchestrator = orch
    resolver = AsyncMock()
    resolver.is_admin = AsyncMock(return_value=False)
    app.state.admin_resolver = resolver
    app.add_middleware(AuthGateMiddleware)
    app.add_middleware(UserContextMiddleware)
    app.include_router(debug_router)
    client = TestClient(app)
    client.resolver = resolver
    return client


def test_viewer_cannot_access_debug_trace(debug_client):
    res = debug_client.get(
        "/api/debug/trace",
        headers={"X-Remote-User-Id": "viewer-1"},
    )
    assert res.status_code == 403


def test_admin_can_access_debug_trace(debug_client):
    debug_client.resolver.is_admin = AsyncMock(return_value=True)
    res = debug_client.get(
        "/api/debug/trace",
        headers={"X-Remote-User-Id": "admin-1"},
    )
    assert res.status_code == 200
