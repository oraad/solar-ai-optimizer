"""Admin-only route guards."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.auth import AuthGateMiddleware, UserContextMiddleware
from app.api.routes import router
from app.models import SystemStatus, utcnow


@pytest.fixture
def guarded_client(monkeypatch):
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
    orch.apply_override = AsyncMock(return_value={"ok": True})
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
    app.include_router(router)
    return TestClient(app)


def test_viewer_cannot_pin_reserve(guarded_client):
    res = guarded_client.post(
        "/api/override",
        json={"reserve_soc": 80},
        headers={"X-Remote-User-Id": "viewer-1"},
    )
    assert res.status_code == 403
    assert "Admin access required" in res.json()["detail"]


def test_viewer_can_pause_engine(guarded_client):
    res = guarded_client.post(
        "/api/override",
        json={"pause_engine": True},
        headers={"X-Remote-User-Id": "viewer-1"},
    )
    assert res.status_code == 200


def test_viewer_can_toggle_shadow(guarded_client):
    res = guarded_client.post(
        "/api/override",
        json={"shadow_mode": False},
        headers={"X-Remote-User-Id": "viewer-1"},
    )
    assert res.status_code == 200


def test_viewer_cannot_force_grid_charge(guarded_client):
    res = guarded_client.post(
        "/api/override",
        json={"force_grid_charge": True},
        headers={"X-Remote-User-Id": "viewer-1"},
    )
    assert res.status_code == 403


def test_viewer_can_read_status(guarded_client):
    res = guarded_client.get("/api/status", headers={"X-Remote-User-Id": "viewer-1"})
    assert res.status_code == 200


def test_viewer_cannot_use_assistant(guarded_client):
    res = guarded_client.post(
        "/api/assistant/ask",
        json={"question": "why grid charge?", "apply": False},
        headers={"X-Remote-User-Id": "viewer-1"},
    )
    assert res.status_code == 403


def test_viewer_cannot_get_config(guarded_client):
    res = guarded_client.get("/api/config", headers={"X-Remote-User-Id": "viewer-1"})
    assert res.status_code == 403


def test_viewer_cannot_list_entities(guarded_client):
    res = guarded_client.get("/api/entities", headers={"X-Remote-User-Id": "viewer-1"})
    assert res.status_code == 403


def test_viewer_mixed_override_denied(guarded_client):
    res = guarded_client.post(
        "/api/override",
        json={"shadow_mode": False, "reserve_soc": 80},
        headers={"X-Remote-User-Id": "viewer-1"},
    )
    assert res.status_code == 403


def test_empty_override_rejected(guarded_client):
    res = guarded_client.post(
        "/api/override",
        json={},
        headers={"X-Remote-User-Id": "viewer-1"},
    )
    assert res.status_code == 400
    assert "No override fields" in res.json()["detail"]
