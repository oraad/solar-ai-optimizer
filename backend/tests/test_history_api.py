"""History REST endpoints return lists."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.auth import AuthGateMiddleware, UserContextMiddleware
from app.api.routes import router
from app.models import SystemStatus, utcnow


@pytest.fixture
def client(monkeypatch):
    orch = MagicMock()
    orch.forecast.site_tz.return_value = ZoneInfo("Asia/Riyadh")
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
    monkeypatch.setenv("API_TOKEN", "history-token")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    from app.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setattr(
        "app.api.routes.repo.get_recent_executions",
        AsyncMock(return_value=[{"ts": "2026-07-08T05:27:00", "capability": "target_soc", "applied": True}]),
    )
    monkeypatch.setattr(
        "app.api.routes.repo.get_recent_shed_executions",
        AsyncMock(return_value=[{"tier": 1, "entity": "switch.pool", "applied": True}]),
    )
    monkeypatch.setattr(
        "app.api.routes.repo.get_recent_decisions",
        AsyncMock(
            return_value=[
                {
                    "ts": "2026-07-08T05:27:00",
                    "cycle_id": "abc123",
                    "target_soc": 80.0,
                    "blackout_risk": "low",
                    "blackout_risk_score": 0.1,
                    "shadow_mode": True,
                    "summary": "test",
                    "reserve_rationale": "",
                    "actions": [],
                    "shed_actions": [],
                    "grid_charge": None,
                    "explanation": None,
                    "engine_active": "rules",
                    "slim": False,
                }
            ]
        ),
    )
    monkeypatch.setattr(
        "app.api.routes.repo.get_decisions_by_cycle_id",
        AsyncMock(return_value=[]),
    )
    app = FastAPI()
    app.state.orchestrator = orch
    app.state.admin_resolver = AsyncMock()
    app.add_middleware(AuthGateMiddleware)
    app.add_middleware(UserContextMiddleware)
    app.include_router(router)
    return TestClient(app)


def test_history_executions(client):
    res = client.get(
        "/api/history/executions?limit=10",
        headers={"Authorization": "Bearer history-token"},
    )
    assert res.status_code == 200
    body = res.json()
    assert "items" in body
    assert "next_cursor" in body
    assert body["items"][0]["capability"] == "target_soc"
    assert body["items"][0]["ts"] == "2026-07-08T08:27:00+03:00"
    assert body["next_cursor"] is None


def test_history_shed_executions(client):
    res = client.get(
        "/api/history/shed-executions?limit=10",
        headers={"Authorization": "Bearer history-token"},
    )
    assert res.status_code == 200
    body = res.json()
    assert "items" in body
    assert "next_cursor" in body
    assert body["items"][0]["tier"] == 1
    assert body["next_cursor"] is None


def test_history_decisions(client):
    res = client.get(
        "/api/history/decisions?limit=10",
        headers={"Authorization": "Bearer history-token"},
    )
    assert res.status_code == 200
    body = res.json()
    assert "items" in body
    assert "next_cursor" in body
    assert body["items"][0]["cycle_id"] == "abc123"
    assert body["items"][0]["ts"] == "2026-07-08T08:27:00+03:00"
    assert body["next_cursor"] is None


def test_history_decisions_with_cycle_id(client):
    res = client.get(
        "/api/history/decisions?limit=10&cycle_id=abc123",
        headers={"Authorization": "Bearer history-token"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["items"] == []
    assert body["next_cursor"] is None
