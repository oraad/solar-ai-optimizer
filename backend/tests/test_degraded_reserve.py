"""Degraded forecast widens reserve buffer."""

from __future__ import annotations

from app.config import BatteryConfig, EngineConfig, ReserveConfig
from app.engine.rules import RuleEngine
from app.grid.reactive import ReactiveGrid
from app.i18n import msg
from app.models import ForecastBundle, Telemetry


def _engine() -> RuleEngine:
    battery = BatteryConfig(capacity_kwh=10.0, min_soc_floor=20.0, max_soc_ceiling=100.0)
    reserve = ReserveConfig(
        critical_load_w=400.0,
        min_autonomy_hours=12.0,
        solar_bridge_buffer_pct=15.0,
        cloudy_extra_buffer_pct=15.0,
    )
    return RuleEngine(battery, reserve, EngineConfig(), ReactiveGrid(battery, reserve))


def test_degraded_forecast_raises_reserve():
    eng = _engine()
    t = Telemetry(battery_soc=80.0, grid_present=False)
    normal = eng.compute_reserve(t, ForecastBundle(degraded=False))
    degraded = eng.compute_reserve(
        t,
        ForecastBundle(
            degraded=True,
            degraded_reasons=[msg("forecast.degraded.stale_solar")],
        ),
    )
    assert degraded.target_soc >= normal.target_soc
    assert degraded.rationale.params.get("extra_degraded") == "yes"
