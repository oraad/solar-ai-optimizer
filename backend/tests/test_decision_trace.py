"""Decision forensics trace assembly."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.services.forensics import build_decision_trace, redact_trace
from app.models import ForecastBundle, Msg, Override, ReserveTarget, SystemStatus, Telemetry, utcnow
from tests.conftest import DUMMY_MSG


@pytest.fixture
def mock_orch():
    orch = MagicMock()
    orch.collector.latest = Telemetry(
        battery_soc=55.0,
        load_power=500.0,
        pv_power=1000.0,
        grid_present=False,
    )
    orch.forecast.current = ForecastBundle(degraded=False)
    orch.latest_grid_stats = None
    orch._plan_flags.return_value = (True, True, True)
    orch._plan_flags.return_value = (True, True, True)
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
    orch.override = Override()
    orch.latest_decision = None
    orch.latest_results = []
    orch.latest_shed_results = []
    orch._telemetry_stale.return_value = False
    orch._telemetry_age_seconds.return_value = 1.0
    orch.cfg.ha.token = "secret-token"
    return orch


def test_build_decision_trace_core_sections(mock_orch):
    trace = build_decision_trace(mock_orch)
    assert "inputs" in trace
    assert "engine" in trace
    assert "overrides" in trace
    assert "decision" in trace
    assert "execution" in trace
    assert "ops" in trace
    assert trace["inputs"]["telemetry"]["battery_soc"] == 55.0


def test_build_decision_trace_sections_filter(mock_orch):
    trace = build_decision_trace(mock_orch, sections="engine,ops")
    assert "engine" in trace
    assert "ops" in trace
    assert "inputs" not in trace


def test_redact_trace_masks_config_token():
    trace = {"config": {"ha": {"token": "leak", "has_token": True}}}
    out = redact_trace(trace)
    assert out["config"]["ha"]["token"] == ""


def test_trace_includes_reserve_when_decision_present(mock_orch):
    mock_orch.latest_decision = MagicMock()
    mock_orch.latest_decision.model_dump.return_value = {}
    # Use real decision path via localize - simplify with None check
    from app.models import BlackoutRisk, Decision

    mock_orch.latest_decision = Decision(
        reserve=ReserveTarget(
            target_soc=60.0,
            solar_bridge_soc=55.0,
            autonomy_floor_soc=40.0,
            rationale=DUMMY_MSG,
        ),
        summary=Msg(key="engine.summary.main"),
        blackout_risk=BlackoutRisk.LOW,
    )
    trace = build_decision_trace(mock_orch, sections="decision")
    assert trace["decision"] is not None
