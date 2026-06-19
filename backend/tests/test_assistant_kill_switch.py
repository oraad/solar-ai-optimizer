"""Assistant kill-switch confirmation gate."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import router
from app.llm.assistant import Assistant
from app.models import SystemStatus, utcnow


def test_kill_switch_requires_confirmation():
    a = Assistant.__new__(Assistant)
    assert a.kill_switch_confirmed("engage kill switch confirm") is True
    assert a.kill_switch_confirmed("kill switch now") is False


@pytest.fixture
def assistant_client():
    orch = MagicMock()
    orch.settings = MagicMock(llm_enabled=False)
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
    orch.shadow_mode = True
    orch.paused = False
    orch.forecast = MagicMock()
    orch.forecast.current = None
    orch.apply_override = AsyncMock()
    app = FastAPI()
    app.state.orchestrator = orch
    app.include_router(router)
    return TestClient(app), orch


def test_assistant_kill_switch_blocked_without_confirm(assistant_client):
    tc, orch = assistant_client
    res = tc.post(
        "/api/assistant/ask",
        json={"question": "kill switch now", "apply": True},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["blocked"] is True
    assert body["block_reason"] == "kill_switch_confirm_required"
    assert body["applied"] is None
    orch.apply_override.assert_not_awaited()
