"""History REST endpoints return lists."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import router
from app.models import SystemStatus, utcnow


@pytest.fixture
def client(monkeypatch):
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
    monkeypatch.setattr(
        "app.api.routes.repo.get_recent_executions",
        AsyncMock(return_value=[{"capability": "target_soc", "applied": True}]),
    )
    monkeypatch.setattr(
        "app.api.routes.repo.get_recent_shed_executions",
        AsyncMock(return_value=[{"tier": 1, "entity": "switch.pool", "applied": True}]),
    )
    app = FastAPI()
    app.state.orchestrator = orch
    app.include_router(router)
    return TestClient(app)


def test_history_executions(client):
    res = client.get("/api/history/executions?limit=10")
    assert res.status_code == 200
    body = res.json()
    assert isinstance(body, list)
    assert body[0]["capability"] == "target_soc"


def test_history_shed_executions(client):
    res = client.get("/api/history/shed-executions?limit=10")
    assert res.status_code == 200
    body = res.json()
    assert isinstance(body, list)
    assert body[0]["tier"] == 1
