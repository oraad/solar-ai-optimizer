"""kWp-aware risk and _load_at nearest-hour lookup."""

from __future__ import annotations

from datetime import timedelta

from app.config import BatteryConfig, EngineConfig, ReserveConfig
from app.engine.rules import RuleEngine
from app.grid.reactive import ReactiveGrid
from app.models import ForecastBundle, LoadForecastPoint, ReserveTarget, SolarForecastPoint, Telemetry, utcnow


def _engine(total_kwp: float = 1.0) -> RuleEngine:
    battery = BatteryConfig(capacity_kwh=10.0, min_soc_floor=20.0, max_soc_ceiling=100.0)
    reserve = ReserveConfig(
        critical_load_w=400.0,
        min_autonomy_hours=12.0,
        solar_bridge_buffer_pct=15.0,
        cloudy_extra_buffer_pct=15.0,
    )
    reactive = ReactiveGrid(battery, reserve)
    eng = RuleEngine(battery, reserve, EngineConfig(), reactive)
    eng.set_total_kwp(total_kwp)
    return eng


def test_load_at_nearest_hour_when_exact_miss():
    eng = _engine()
    now = utcnow().replace(minute=0, second=0, microsecond=0)
    forecast = ForecastBundle(
        solar=[],
        load=[
            LoadForecastPoint(ts=now + timedelta(hours=2), load_power_w=900.0),
        ],
    )
    # Hour 1 is missing; nearest within 3600s is hour 2.
    load_w = eng._load_at(forecast, now + timedelta(hours=1))  # noqa: SLF001
    assert load_w == 900.0


def test_load_at_falls_back_to_critical_when_far():
    eng = _engine()
    now = utcnow().replace(minute=0, second=0, microsecond=0)
    forecast = ForecastBundle(
        solar=[],
        load=[
            LoadForecastPoint(ts=now + timedelta(hours=5), load_power_w=900.0),
        ],
    )
    load_w = eng._load_at(forecast, now)  # noqa: SLF001
    assert load_w == 400.0


def test_blackout_risk_uses_configured_kwp():
    eng_small = _engine(total_kwp=1.0)
    eng_large = _engine(total_kwp=10.0)
    t = Telemetry(battery_soc=50.0, grid_present=False)
    reserve = ReserveTarget(
        target_soc=60.0,
        autonomy_floor_soc=40.0,
        solar_bridge_soc=55.0,
        rationale="test",
    )
    # Same absolute yield is worse for a larger array (3 kWh vs 5 vs 50 kWh clear-sky).
    forecast = ForecastBundle(solar=[], load=[], solar_tomorrow_kwh=3.0)
    _, score_small = eng_small._blackout_risk(t, reserve, forecast)  # noqa: SLF001
    _, score_large = eng_large._blackout_risk(t, reserve, forecast)  # noqa: SLF001
    assert score_large > score_small
