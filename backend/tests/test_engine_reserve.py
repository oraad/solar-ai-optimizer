"""Tests for the reserve-floor and blackout-risk logic (no I/O)."""

from __future__ import annotations

from datetime import timedelta

from app.config import BatteryConfig, EngineConfig, ReserveConfig
from app.engine.rules import RuleEngine
from app.grid.reactive import ReactiveGrid
from app.models import (
    BlackoutRisk,
    ForecastBundle,
    LoadForecastPoint,
    SolarForecastPoint,
    Telemetry,
    utcnow,
)


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
    return ForecastBundle(solar=solar, load=load)


def test_autonomy_floor_sets_minimum():
    eng = _engine()
    # No solar/load forecast -> autonomy floor governs.
    t = Telemetry(battery_soc=80.0, grid_present=False)
    target = eng.compute_reserve(t, None)
    # 12h * 400W = 4.8 kWh of 10 kWh = 48% -> above the 20% hard floor.
    assert target.autonomy_floor_soc >= 48.0 - 0.5
    assert target.target_soc >= target.autonomy_floor_soc - 0.001


def test_solar_bridge_higher_when_no_sun():
    eng = _engine()
    t = Telemetry(battery_soc=80.0, grid_present=False)
    dark = eng.compute_reserve(t, _flat_forecast(load_w=500, solar_w=0))
    sunny = eng.compute_reserve(t, _flat_forecast(load_w=500, solar_w=3000))
    assert dark.target_soc >= sunny.target_soc


def test_blackout_risk_critical_at_floor():
    eng = _engine()
    t = Telemetry(battery_soc=20.0, grid_present=False)
    decision = eng.decide(t, _flat_forecast(500, 0), None, None, shadow_mode=True)
    assert decision.blackout_risk == BlackoutRisk.CRITICAL


def test_decision_does_not_emit_min_soc_write():
    eng = _engine()
    t = Telemetry(battery_soc=70.0, grid_present=False)
    decision = eng.decide(t, _flat_forecast(400, 1000), None, None, shadow_mode=True)
    caps = {a.capability.value for a in decision.actions}
    assert "min_soc" not in caps
