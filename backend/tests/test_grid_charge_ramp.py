"""Grid charge ramp engine and decision integration tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.config import BatteryConfig, EngineConfig, GridChargeConfig, GridChargeFactor, ReserveConfig
from app.engine.rules import RuleEngine
from app.grid.ramp import RampContext, _eval_solar_bridge, _remaining_solar_wh, compute_ramp_plan
from app.grid.reactive import ReactiveGrid
from app.models import (
    BlackoutRisk,
    ForecastBundle,
    GridStats,
    LoadForecastPoint,
    ReserveTarget,
    SolarForecastPoint,
    Telemetry,
    utcnow,
)
from tests.conftest import DUMMY_MSG


def _battery(**kwargs) -> BatteryConfig:
    defaults = dict(
        capacity_kwh=10.0,
        nominal_voltage=51.2,
        min_soc_floor=20.0,
        max_soc_ceiling=100.0,
    )
    defaults.update(kwargs)
    return BatteryConfig(**defaults)


def _grid_charge(**kwargs) -> GridChargeConfig:
    defaults = dict(ramp_enabled=True, max_grid_charge_a=60.0)
    defaults.update(kwargs)
    return GridChargeConfig(**defaults)


def _telemetry(**kwargs) -> Telemetry:
    defaults = dict(
        battery_soc=40.0,
        grid_present=True,
        pv_power=500.0,
        load_power=1500.0,
        battery_power=800.0,
    )
    defaults.update(kwargs)
    return Telemetry(**defaults)


def _reserve(target: float = 55.0) -> ReserveTarget:
    return ReserveTarget(
        target_soc=target,
        solar_bridge_soc=target,
        autonomy_floor_soc=30.0,
        rationale=DUMMY_MSG,
    )


def _ctx(**kwargs) -> RampContext:
    battery = kwargs.pop("battery", _battery())
    grid_charge = kwargs.pop("grid_charge", _grid_charge())
    defaults = dict(
        telemetry=_telemetry(),
        forecast=None,
        grid_stats=GridStats(avg_window_minutes=30.0),
        reserve=_reserve(),
        target_soc=55.0,
        blackout_risk=BlackoutRisk.MODERATE,
        blackout_risk_score=0.4,
        battery=battery,
        grid_charge=grid_charge,
        last_amps=None,
    )
    defaults.update(kwargs)
    return RampContext(**defaults)


def test_cap_chain_order_affects_output():
    high_soc = _ctx(
        grid_charge=GridChargeConfig(
            factor_order=[GridChargeFactor.soc_gap],
            ramp_step_a=100.0,
            min_grid_charge_a=0.0,
        ),
        telemetry=_telemetry(battery_soc=50.0),
    )
    low_soc = _ctx(
        grid_charge=GridChargeConfig(
            factor_order=[GridChargeFactor.soc_gap],
            ramp_step_a=100.0,
            min_grid_charge_a=0.0,
        ),
        telemetry=_telemetry(battery_soc=25.0),
    )
    high_plan = compute_ramp_plan(high_soc)
    low_plan = compute_ramp_plan(low_soc)
    assert low_plan.target_amps > high_plan.target_amps


def test_battery_power_lowers_ceiling():
    ctx = _ctx(
        grid_charge=GridChargeConfig(
            factor_order=[GridChargeFactor.battery_power],
            ramp_step_a=100.0,
            min_grid_charge_a=0.0,
        ),
        telemetry=_telemetry(battery_power=2500.0),
    )
    idle = _ctx(
        grid_charge=GridChargeConfig(
            factor_order=[GridChargeFactor.battery_power],
            ramp_step_a=100.0,
            min_grid_charge_a=0.0,
        ),
        telemetry=_telemetry(battery_power=-200.0),
    )
    charging = compute_ramp_plan(ctx)
    not_charging = compute_ramp_plan(idle)
    assert charging.target_amps < not_charging.target_amps


def test_ramp_step_limits_delta():
    ctx = _ctx(
        grid_charge=GridChargeConfig(ramp_step_a=5.0, min_grid_charge_a=0.0),
        last_amps=10.0,
    )
    plan = compute_ramp_plan(ctx)
    assert plan.target_amps <= 15.0


def test_grid_absent_disables():
    ctx = _ctx(telemetry=_telemetry(grid_present=False))
    plan = compute_ramp_plan(ctx)
    assert not plan.enabled
    assert plan.target_amps == 0.0


def test_legacy_max_or_off_when_ramp_disabled():
    reactive = ReactiveGrid(_battery(), ReserveConfig(), GridChargeConfig(ramp_enabled=False))
    result = reactive.opportunistic_actions(_telemetry(battery_soc=40.0), 55.0)
    assert result.plan.enabled
    assert result.plan.target_amps == 60.0
    assert any(a.capability.value == "max_grid_charge_current" for a in result.actions)


def test_decision_includes_grid_charge():
    reactive = ReactiveGrid(_battery(), ReserveConfig(), GridChargeConfig(ramp_enabled=True))
    engine = RuleEngine(
        _battery(),
        ReserveConfig(),
        EngineConfig(),
        reactive,
        grid_charge=GridChargeConfig(ramp_enabled=True, ramp_step_a=100.0),
    )
    decision = engine.decide(
        _telemetry(battery_soc=40.0),
        None,
        GridStats(avg_window_minutes=25.0),
        None,
        shadow_mode=True,
    )
    assert decision.grid_charge is not None
    assert decision.grid_charge.enabled
    assert decision.grid_charge.target_amps > 0


def test_force_override_bypasses_ramp():
    from app.models import Override

    reactive = ReactiveGrid(_battery(), ReserveConfig(), GridChargeConfig(ramp_enabled=True))
    engine = RuleEngine(
        _battery(),
        ReserveConfig(),
        EngineConfig(),
        reactive,
        grid_charge=GridChargeConfig(ramp_enabled=True),
    )
    decision = engine.decide(
        _telemetry(battery_soc=40.0),
        None,
        None,
        Override(force_grid_charge=True),
        shadow_mode=True,
    )
    assert decision.grid_charge is not None
    assert decision.grid_charge.target_amps == 60.0
    assert decision.grid_charge.rationale.key == "engine.override.force_grid_charge_plan"


def test_remaining_solar_lowers_when_plentiful():
    now = utcnow().replace(minute=0, second=0, microsecond=0)
    solar = [
        SolarForecastPoint(
            ts=now + timedelta(hours=i),
            pv_power_w=3000.0,
            pv_energy_wh=3000.0,
        )
        for i in range(8)
    ]
    forecast = ForecastBundle(
        solar=solar,
        load=[LoadForecastPoint(ts=now, load_power_w=500.0)],
    )
    ctx = _ctx(
        grid_charge=GridChargeConfig(
            factor_order=[
                GridChargeFactor.soc_gap,
                GridChargeFactor.remaining_solar_today,
            ],
            ramp_step_a=100.0,
            min_grid_charge_a=0.0,
        ),
        forecast=forecast,
        telemetry=_telemetry(battery_soc=50.0),
    )
    without_solar = _ctx(
        grid_charge=GridChargeConfig(
            factor_order=[GridChargeFactor.soc_gap],
            ramp_step_a=100.0,
            min_grid_charge_a=0.0,
        ),
        telemetry=_telemetry(battery_soc=50.0),
    )
    with_solar = compute_ramp_plan(ctx)
    no_solar = compute_ramp_plan(without_solar)
    assert with_solar.target_amps < no_solar.target_amps


def test_stale_telemetry_disables_grid_charge():
    reactive = ReactiveGrid(_battery(), ReserveConfig(), GridChargeConfig(ramp_enabled=True))
    engine = RuleEngine(
        _battery(),
        ReserveConfig(),
        EngineConfig(),
        reactive,
        grid_charge=GridChargeConfig(ramp_enabled=True),
    )
    decision = engine.decide(
        _telemetry(battery_soc=40.0, grid_present=True),
        None,
        GridStats(avg_window_minutes=25.0),
        None,
        shadow_mode=False,
        telemetry_stale=True,
    )
    assert decision.grid_charge is not None
    assert not decision.grid_charge.enabled
    assert decision.grid_charge.target_amps == 0.0
    assert any(a.capability.value == "grid_charge_enable" and a.value is False for a in decision.actions)
    assert any(
        a.capability.value == "max_grid_charge_current" and a.value == 0.0 for a in decision.actions
    )


def test_solar_bridge_at_target_no_floor():
    bridge = 50.0
    ctx = _ctx(
        reserve=ReserveTarget(
            target_soc=55.0,
            solar_bridge_soc=bridge,
            autonomy_floor_soc=30.0,
            rationale=DUMMY_MSG,
        ),
        target_soc=55.0,
        telemetry=_telemetry(battery_soc=bridge),
    )
    result = _eval_solar_bridge(ctx)
    assert result.ceiling_a == 60.0


def test_remaining_solar_respects_site_timezone(monkeypatch):
    from zoneinfo import ZoneInfo

    tz = ZoneInfo("Africa/Johannesburg")
    # 20:00 UTC = 22:00 local on June 21
    now = datetime(2026, 6, 21, 20, 0, tzinfo=timezone.utc)
    monkeypatch.setattr("app.grid.ramp.utcnow", lambda: now)

    late_utc = datetime(2026, 6, 21, 22, 0, tzinfo=timezone.utc)
    forecast = ForecastBundle(
        solar=[
            SolarForecastPoint(ts=late_utc, pv_power_w=1000.0, pv_energy_wh=1000.0),
        ],
        load=[],
    )
    utc_ctx = _ctx(forecast=forecast, site_timezone="auto")
    local_ctx = _ctx(forecast=forecast, site_timezone="Africa/Johannesburg")

    utc_wh = _remaining_solar_wh(utc_ctx, now)
    local_wh = _remaining_solar_wh(local_ctx, now)
    assert utc_wh == 1000.0
    assert local_wh == 0.0
