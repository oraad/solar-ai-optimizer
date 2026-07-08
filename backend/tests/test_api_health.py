"""API health contract tests."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import router
from app.models import SystemStatus, utcnow


@pytest.fixture
def client():
    orch = MagicMock()
    orch.ha.is_reachable.return_value = True
    orch.shadow_mode = True
    orch.paused = False
    orch.forecast.current = None
    orch.forecast.site_tz.return_value = ZoneInfo("Asia/Riyadh")
    orch.build_status.return_value = SystemStatus(
        ha_connected=True,
        telemetry_stale=False,
        telemetry_age_seconds=5.0,
        forecast_misconfigured=False,
        forecast_degraded=False,
        engine_mode="rules",
        engine_active="rules",
        shadow_mode=True,
        paused=False,
        last_updated=utcnow(),
    )
    fs = MagicMock()
    fs.heartbeat_enabled = True
    fs.heartbeat_entity = "input_datetime.test"
    orch.cfg.fail_safe = fs
    orch.heartbeat.last_pulse_at = datetime(2026, 7, 8, 5, 27, tzinfo=timezone.utc)
    app = FastAPI()
    app.state.orchestrator = orch
    app.include_router(router)
    return TestClient(app)


def test_health_includes_monitoring_fields(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert "telemetry_stale" in body
    assert "engine_active" in body
    assert "metrics" in body
    assert "control_cycles" in body["metrics"]
    assert "heartbeat_configured" in body
    assert body["heartbeat_configured"] is True
    assert body["heartbeat_last_pulse"] == "2026-07-08T08:27:00+03:00"
    assert body["time"].endswith("+03:00")
