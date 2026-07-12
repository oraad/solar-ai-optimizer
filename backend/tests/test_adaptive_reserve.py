"""Adaptive load-aware autonomy floor and solar-bridge."""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

from app.config import BatteryConfig, EngineConfig, OptimizationPriority, ReserveConfig
from app.engine.priorities import (
    adaptive_load_scale,
    autonomy_hours_scale,
    effective_critical_w,
    mean_load_power_w,
    smoothed_adaptive_load_w,
)
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


def _engine(
    *,
    adaptive: bool = True,
    priority_order: list[OptimizationPriority] | None = None,
    adaptive_cap_w: float | None = None,
) -> RuleEngine:
    battery = BatteryConfig(capacity_kwh=10.0, min_soc_floor=20.0, max_soc_ceiling=100.0)
    reserve = ReserveConfig(
        critical_load_w=400.0,
        min_autonomy_hours=12.0,
        solar_bridge_buffer_pct=15.0,
        cloudy_extra_buffer_pct=15.0,
        adaptive_load_enabled=adaptive,
        adaptive_load_cap_w=adaptive_cap_w,
    )
    reactive = ReactiveGrid(battery, reserve)
    cfg = EngineConfig(priority_order=priority_order) if priority_order else EngineConfig()
    return RuleEngine(battery, reserve, cfg, reactive)


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


def test_mean_load_requires_min_samples():
    assert mean_load_power_w([100.0, 200.0], min_samples=3, fallback=50.0) == 50.0
    assert mean_load_power_w([100.0, 200.0, 300.0], min_samples=3) == 200.0


def test_smoothed_adaptive_max_load_and_discharge():
    rows = [
        SimpleNamespace(load_power=300.0, battery_power=-900.0),
        SimpleNamespace(load_power=320.0, battery_power=-880.0),
        SimpleNamespace(load_power=310.0, battery_power=-920.0),
    ]
    tel = Telemetry(battery_soc=80.0, load_power=310.0, battery_power=-900.0)
    smooth, dis = smoothed_adaptive_load_w(rows, tel)
    assert dis is not None and dis > 800.0
    assert smooth == max((300 + 320 + 310) / 3, dis)


def test_smoothed_adaptive_discharge_only():
    rows = [
        SimpleNamespace(load_power=None, battery_power=-700.0),
        SimpleNamespace(load_power=None, battery_power=-750.0),
        SimpleNamespace(load_power=None, battery_power=-800.0),
    ]
    tel = Telemetry(battery_soc=80.0, battery_power=-750.0)
    smooth, dis = smoothed_adaptive_load_w(rows, tel)
    assert smooth == dis
    assert smooth is not None and smooth == 750.0


def test_adaptive_off_identity():
    eng = _engine(adaptive=False)
    t = Telemetry(battery_soc=80.0, grid_present=False, load_power=1200.0)
    target = eng.compute_reserve(t, None, smoothed_load_w=1200.0)
    # 12h * 400W = 4.8 kWh / 10 kWh = 48%
    assert target.autonomy_floor_soc == 48.0
    assert target.effective_critical_w == 400.0
    assert target.adaptive_blend_a == 0.0
    assert target.smoothed_load_w is None
    assert target.smoothed_discharge_w is None


def test_empty_history_uses_critical_when_no_smooth():
    eng = _engine(adaptive=True)
    t = Telemetry(battery_soc=80.0, grid_present=False)
    target = eng.compute_reserve(t, None, smoothed_load_w=None)
    assert target.autonomy_floor_soc == 48.0
    assert target.effective_critical_w == 400.0


def test_discharge_only_raises_floor():
    eng = _engine(adaptive=True)
    t = Telemetry(battery_soc=80.0, grid_present=False, battery_power=-1000.0)
    target = eng.compute_reserve(t, None, smoothed_load_w=None)
    assert target.effective_critical_w is not None
    assert target.effective_critical_w > 400.0
    assert target.autonomy_floor_soc > 48.0
    assert target.smoothed_discharge_w == 1000.0


def test_high_discharge_raises_above_low_load_alone():
    eng = _engine(adaptive=True)
    t = Telemetry(battery_soc=80.0, grid_present=False)
    low = eng.compute_reserve(
        t, None, smoothed_load_w=500.0, smoothed_discharge_w=None, update_hysteresis=False
    )
    eng2 = _engine(adaptive=True)
    high = eng2.compute_reserve(
        t, None, smoothed_load_w=900.0, smoothed_discharge_w=900.0, update_hysteresis=False
    )
    assert high.effective_critical_w > low.effective_critical_w


def test_resilience_first_higher_floor_than_savings_first():
    smooth = 1000.0
    resilient = _engine(
        priority_order=[
            OptimizationPriority.resilience,
            OptimizationPriority.savings,
            OptimizationPriority.self_sufficiency,
        ]
    )
    savings = _engine(
        priority_order=[
            OptimizationPriority.savings,
            OptimizationPriority.resilience,
            OptimizationPriority.self_sufficiency,
        ]
    )
    t = Telemetry(battery_soc=80.0, grid_present=False)
    r = resilient.compute_reserve(t, None, smoothed_load_w=smooth)
    s = savings.compute_reserve(t, None, smoothed_load_w=smooth)
    assert r.autonomy_floor_soc > s.autonomy_floor_soc
    assert r.effective_critical_w > s.effective_critical_w
    assert r.adaptive_blend_a > s.adaptive_blend_a


def test_bridge_floors_at_effective_critical():
    eng = _engine(adaptive=True)
    t = Telemetry(battery_soc=80.0, grid_present=False)
    # Forecast load below effective critical; bridge should still size on Leff.
    low_fc = eng.compute_reserve(
        t, _flat_forecast(load_w=100.0, solar_w=0.0), smoothed_load_w=800.0
    )
    high_fc = eng.compute_reserve(
        t, _flat_forecast(load_w=900.0, solar_w=0.0), smoothed_load_w=800.0
    )
    assert low_fc.solar_bridge_soc > 48.0
    assert high_fc.solar_bridge_soc >= low_fc.solar_bridge_soc


def test_hysteresis_slows_downward_moves():
    crit = 400.0
    high, _ = effective_critical_w(
        critical_load_w=crit,
        smoothed_load_w=1000.0,
        adaptive_enabled=True,
        adaptive_cap_w=None,
        resilience_weight=1.0,
        savings_weight=0.4,
        self_sufficiency_weight=0.15,
        prev_effective_w=None,
    )
    used, _ = effective_critical_w(
        critical_load_w=crit,
        smoothed_load_w=400.0,
        adaptive_enabled=True,
        adaptive_cap_w=None,
        resilience_weight=1.0,
        savings_weight=0.4,
        self_sufficiency_weight=0.15,
        prev_effective_w=high,
        hysteresis_down_frac=0.10,
    )
    assert used > crit
    assert used >= high * 0.90 - 1e-6
    assert used < high


def test_cap_is_hard_after_hysteresis():
    used, _ = effective_critical_w(
        critical_load_w=400.0,
        smoothed_load_w=500.0,
        adaptive_enabled=True,
        adaptive_cap_w=600.0,
        resilience_weight=1.0,
        savings_weight=0.4,
        self_sufficiency_weight=0.15,
        prev_effective_w=2000.0,
        hysteresis_down_frac=0.10,
    )
    assert used <= 600.0


def test_engine_hysteresis_across_cycles():
    eng = _engine(adaptive=True)
    t = Telemetry(battery_soc=80.0, grid_present=False)
    first = eng.compute_reserve(t, None, smoothed_load_w=1000.0)
    second = eng.compute_reserve(t, None, smoothed_load_w=400.0)
    assert second.effective_critical_w is not None
    assert first.effective_critical_w is not None
    assert second.effective_critical_w > 400.0
    assert second.effective_critical_w < first.effective_critical_w


def test_update_hysteresis_false_preserves_prev():
    eng = _engine(adaptive=True)
    t = Telemetry(battery_soc=80.0, grid_present=False)
    eng.compute_reserve(t, None, smoothed_load_w=1000.0)
    prev = eng.last_effective_critical_w
    eng.compute_reserve(
        t, None, smoothed_load_w=400.0, update_hysteresis=False
    )
    assert eng.last_effective_critical_w == prev


def test_autonomy_hours_scale_demotes_when_resilience_last():
    assert autonomy_hours_scale(1.0) == 1.0
    assert autonomy_hours_scale(0.15) == 0.85


def test_default_adaptive_scale_is_identity_friendly():
    assert adaptive_load_scale(1.0, 0.4, 0.15) == 1.0


def test_adaptive_scale_never_below_floor():
    # Resilience last + savings 1st + self-sufficiency would lean hardest.
    a = adaptive_load_scale(0.15, 1.0, 1.0)
    assert a >= 0.35


def test_mpc_pin_not_below_rules():
    eng = _engine(adaptive=False)
    t = Telemetry(battery_soc=80.0, grid_present=False)
    forecast = _flat_forecast(load_w=500.0, solar_w=0.0)
    rules = eng.compute_reserve(t, forecast, update_hysteresis=False)
    decision = eng.decide(
        t,
        forecast,
        None,
        None,
        shadow_mode=True,
        mpc_reserve=rules.target_soc - 20.0,
        update_hysteresis=False,
    )
    assert decision.reserve.target_soc >= rules.target_soc - 0.001
    assert decision.reserve.source.value == "mpc"


def test_mpc_missing_forecast_does_not_force_critical():
    from app.engine.mpc import MPCEngine

    battery = BatteryConfig(capacity_kwh=10.0, min_soc_floor=20.0, max_soc_ceiling=100.0)
    reserve = ReserveConfig(critical_load_w=400.0, min_autonomy_hours=12.0)
    engine_cfg = EngineConfig(mode="mpc")
    reactive = ReactiveGrid(battery, reserve)
    rules = RuleEngine(battery, reserve, engine_cfg, reactive)
    mpc = MPCEngine(battery, reserve, engine_cfg, rule_engine=rules)
    t = Telemetry(battery_soc=80.0, grid_present=True)
    decision = mpc.decide(t, None, None, None, True, reactive)
    assert decision.blackout_risk != BlackoutRisk.CRITICAL
