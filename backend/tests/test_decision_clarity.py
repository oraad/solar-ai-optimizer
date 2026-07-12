"""Decision clarity: cycle_id, explanation, MPC attribution, causality trace."""

from __future__ import annotations

from datetime import timedelta

from app.config import BatteryConfig, EngineConfig, ReserveConfig
from app.engine.rules import RuleEngine
from app.grid.reactive import ReactiveGrid
from app.models import (
    ForecastBundle,
    LoadForecastPoint,
    Override,
    ReserveSource,
    SolarForecastPoint,
    Telemetry,
    utcnow,
)
from app.services.forensics import DEFAULT_SECTIONS, _parse_sections


def _engine() -> RuleEngine:
    battery = BatteryConfig(capacity_kwh=10.0, min_soc_floor=20.0, max_soc_ceiling=100.0)
    reserve = ReserveConfig(
        critical_load_w=400.0,
        min_autonomy_hours=12.0,
        solar_bridge_buffer_pct=15.0,
        cloudy_extra_buffer_pct=15.0,
    )
    reactive = ReactiveGrid(battery, reserve)
    return RuleEngine(battery, reserve, EngineConfig(), reactive)


def _flat_forecast(load_w: float, solar_w: float, hours: int = 48) -> ForecastBundle:
    now = utcnow().replace(minute=0, second=0, microsecond=0)
    solar = [
        SolarForecastPoint(ts=now + timedelta(hours=i), pv_power_w=solar_w, pv_energy_wh=solar_w)
        for i in range(hours)
    ]
    load = [
        LoadForecastPoint(ts=now + timedelta(hours=i), load_power_w=load_w)
        for i in range(hours)
    ]
    return ForecastBundle(solar=solar, load=load, solar_tomorrow_kwh=5.0)


def test_decision_has_cycle_id_and_explanation():
    eng = _engine()
    t = Telemetry(battery_soc=70.0, grid_present=True, pv_power=1000, load_power=500)
    d = eng.decide(t, _flat_forecast(400, 1000), None, None, shadow_mode=True)
    assert d.cycle_id
    assert d.explanation is not None
    assert d.explanation.schema_version == 1
    assert d.reserve.source == ReserveSource.RULES
    assert any(s.id == "reserve" for s in d.explanation.steps)


def test_operator_pin_source_not_confused_with_mpc():
    eng = _engine()
    t = Telemetry(battery_soc=70.0, grid_present=False)
    ov = Override(reserve_soc=90.0)
    d = eng.decide(
        t,
        _flat_forecast(400, 0),
        None,
        ov,
        shadow_mode=True,
        mpc_reserve=55.0,
    )
    assert d.reserve.source == ReserveSource.OPERATOR
    assert d.reserve.target_soc == 90.0
    assert d.explanation is not None
    assert d.explanation.reserve.source == ReserveSource.OPERATOR


def test_mpc_reserve_pin_source():
    eng = _engine()
    t = Telemetry(battery_soc=70.0, grid_present=False)
    forecast = _flat_forecast(400, 0)
    rules = eng.compute_reserve(t, forecast, update_hysteresis=False)
    d = eng.decide(
        t,
        forecast,
        None,
        None,
        shadow_mode=True,
        mpc_reserve=66.0,
        update_hysteresis=False,
    )
    assert d.reserve.source == ReserveSource.MPC
    # MPC pin cannot undercut rules reserve.
    assert d.reserve.target_soc == max(66.0, rules.target_soc)
    assert d.explanation is not None
    assert d.explanation.reserve.mpc_soc == d.reserve.target_soc


def test_forensics_sections_include_causality_and_reasoning_alias():
    assert "causality" in DEFAULT_SECTIONS
    parsed = _parse_sections("reasoning,execution")
    assert "decision" in parsed
    assert "causality" in parsed
    assert "execution" in parsed
