"""Rule engine plan_* flags for disabled subsystems."""

from __future__ import annotations

from app.config import BatteryConfig, EngineConfig, GridChargeConfig, ReserveConfig
from app.engine.rules import RuleEngine
from app.grid.reactive import ReactiveGrid
from app.i18n.serialize import msg_text
from app.models import Telemetry


def _engine() -> RuleEngine:
    battery = BatteryConfig(capacity_kwh=10.0, min_soc_floor=20.0, max_soc_ceiling=100.0)
    reserve = ReserveConfig(critical_load_w=400.0, min_autonomy_hours=12.0)
    reactive = ReactiveGrid(battery, reserve)
    return RuleEngine(battery, reserve, EngineConfig(), reactive)


def test_decide_optimization_disabled_uses_static_reserve():
    eng = _engine()
    t = Telemetry(battery_soc=55.0, grid_present=True)
    decision = eng.decide(
        t,
        None,
        None,
        None,
        shadow_mode=True,
        plan_optimization=False,
    )
    assert decision.reserve.target_soc == 55.0
    assert "optimization disabled" in msg_text(decision.reserve.rationale).lower()
    assert "shedding active" in msg_text(decision.summary).lower()
    assert decision.blackout_risk_score == 0.0


def test_decide_grid_charge_disabled_skips_actions():
    eng = _engine()
    t = Telemetry(battery_soc=70.0, grid_present=True)
    decision = eng.decide(
        t,
        None,
        None,
        None,
        shadow_mode=True,
        plan_grid_charge=False,
    )
    assert decision.grid_charge is None
    assert decision.actions == []


def test_decide_shedding_disabled_skips_shed_actions():
    eng = _engine()
    t = Telemetry(battery_soc=70.0, grid_present=True)
    decision = eng.decide(
        t,
        None,
        None,
        None,
        shadow_mode=True,
        plan_shedding=False,
    )
    assert decision.shed_actions == []
