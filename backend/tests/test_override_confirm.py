"""REST kill switch requires confirm=true."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import router
from app.models import SystemStatus, utcnow


@pytest.fixture
def client():
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
    app = FastAPI()
    app.state.orchestrator = orch
    app.include_router(router)
    return TestClient(app), orch


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
