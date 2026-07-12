"""Opportunity-window merge, trusted remaining, and import-cap helpers."""

from __future__ import annotations

from datetime import timedelta

import pytest

from app.config import BatteryConfig, GridChargeConfig, ReserveConfig
from app.engine.priorities import grid_present_risk_multiplier
from app.grid.opportunity import (
    avg_opportunity_minutes,
    merge_opportunity_windows,
    present_elapsed_minutes,
    trusted_window_minutes,
)
from app.grid.reactive import ReactiveGrid
from app.grid.ramp import RampContext, compute_ramp_plan
from app.ha.power_units import effective_max_grid_charge_a, power_watts_from_ha_state

from app.models import (
    BlackoutRisk,
    ForecastBundle,
    GridEvent,
    GridStats,
    Msg,
    ReserveTarget,
    Telemetry,
    utcnow,
)


def test_merge_flicker_inside_two_hour_window():
    """User example: short outages inside ~10:00–11:55 merge to one opportunity."""
    now = utcnow().replace(minute=0, second=0, microsecond=0)
    t0 = now - timedelta(hours=2)
    # Build raw intervals with flicker
    intervals = [
        (t0, t0 + timedelta(minutes=10), True),
        (t0 + timedelta(minutes=10), t0 + timedelta(minutes=20), False),  # 10m out
        (t0 + timedelta(minutes=20), t0 + timedelta(minutes=30), True),
        (t0 + timedelta(minutes=30), t0 + timedelta(minutes=30, seconds=30), False),
        (t0 + timedelta(minutes=30, seconds=30), t0 + timedelta(minutes=40), True),
        (t0 + timedelta(minutes=40), t0 + timedelta(minutes=42), False),  # 2m flicker
        (t0 + timedelta(minutes=42), t0 + timedelta(minutes=50), True),
        (t0 + timedelta(minutes=50), t0 + timedelta(minutes=65), False),  # 15m out
        (t0 + timedelta(minutes=65), t0 + timedelta(minutes=115), True),
    ]
    opps = merge_opportunity_windows(intervals, max_outage_ignore_minutes=30)
    assert len(opps) == 1
    assert (opps[0][1] - opps[0][0]).total_seconds() / 60.0 == pytest.approx(115.0)


def test_long_gap_splits_opportunity():
    now = utcnow()
    intervals = [
        (now, now + timedelta(minutes=30), True),
        (now + timedelta(minutes=30), now + timedelta(minutes=80), False),  # 50m
        (now + timedelta(minutes=80), now + timedelta(minutes=100), True),
    ]
    opps = merge_opportunity_windows(intervals, max_outage_ignore_minutes=30)
    assert len(opps) == 2


def test_elapsed_from_merged_onset_not_last_present_edge():
    now = utcnow()
    start = now - timedelta(minutes=60)
    intervals = [
        (start, start + timedelta(minutes=20), True),
        (start + timedelta(minutes=20), start + timedelta(minutes=25), False),
        (start + timedelta(minutes=25), now + timedelta(minutes=5), True),
    ]
    opps = merge_opportunity_windows(intervals, 30)
    elapsed = present_elapsed_minutes(opps, now)
    assert elapsed is not None
    assert elapsed == pytest.approx(60.0, abs=0.1)


def test_trusted_cold_start_uses_max_continuous():
    assert trusted_window_minutes(
        avg_window_minutes=0.0,
        max_continuous_minutes=120.0,
        safety_factor=0.75,
    ) == pytest.approx(90.0)


def test_power_watts_kw_and_w():
    assert power_watts_from_ha_state(
        {"state": "5.5", "attributes": {"unit_of_measurement": "kW"}}
    ) == pytest.approx(5500.0)
    assert power_watts_from_ha_state(
        {"state": "5500", "attributes": {"unit_of_measurement": "W"}}
    ) == pytest.approx(5500.0)


def test_effective_max_charge_a_import_cap():
    # 3000 W / 50 V = 60 A → same as max; 2000 W → 40 A
    assert effective_max_grid_charge_a(
        max_grid_charge_a=60.0, nominal_voltage=50.0, site_import_w=2000.0
    ) == pytest.approx(40.0)


def test_risk_fade_toward_one_near_end_of_window():
    base = grid_present_risk_multiplier(1.0, 0.4)
    faded = grid_present_risk_multiplier(
        1.0,
        0.4,
        present_elapsed_minutes=80.0,
        remaining_window_minutes=10.0,
    )
    assert faded > base
    assert faded < 1.0 + 1e-9


@pytest.mark.asyncio
async def test_compute_stats_merged_avg_and_remaining(monkeypatch: pytest.MonkeyPatch):
    now = utcnow()
    start = now - timedelta(minutes=50)
    events = [
        GridEvent(ts=start, grid_present=True),
        GridEvent(ts=start + timedelta(minutes=10), grid_present=False),
        GridEvent(ts=start + timedelta(minutes=15), grid_present=True),
    ]

    async def fake_events(since):
        return [e for e in events if e.ts >= since]

    async def fake_last():
        return events[-1]

    async def fake_state_at(_when):
        return False

    monkeypatch.setattr("app.grid.reactive.repo.get_grid_events_since", fake_events)
    monkeypatch.setattr("app.grid.reactive.repo.get_last_grid_event", fake_last)

    gc = GridChargeConfig(
        max_continuous_present_minutes=120.0,
        grid_window_safety_factor=0.75,
        max_outage_ignore_minutes=30.0,
    )
    grid = ReactiveGrid(BatteryConfig(), ReserveConfig(), grid_charge=gc)
    monkeypatch.setattr(grid, "_state_at", fake_state_at)

    stats = await grid.compute_stats(now=now, live_present=True)
    assert stats.avg_window_minutes >= 45.0  # merged ~50 min
    assert stats.present_elapsed_minutes is not None
    assert stats.remaining_window_minutes is not None
    assert stats.remaining_window_minutes >= 0.0


def test_live_absent_still_zero_amps():
    battery = BatteryConfig(nominal_voltage=50.0)
    gc = GridChargeConfig(max_grid_charge_a=60.0)
    reserve = ReserveTarget(
        target_soc=80.0,
        solar_bridge_soc=80.0,
        autonomy_floor_soc=20.0,
        rationale=Msg(key=""),
    )
    ctx = RampContext(
        telemetry=Telemetry(battery_soc=50.0, grid_present=False),
        forecast=None,
        grid_stats=GridStats(
            remaining_window_minutes=10.0, currently_present=False
        ),
        reserve=reserve,
        target_soc=80.0,
        blackout_risk=BlackoutRisk.LOW,
        blackout_risk_score=0.1,
        battery=battery,
        grid_charge=gc,
        effective_max_charge_a=40.0,
    )
    plan = compute_ramp_plan(ctx)
    assert plan.enabled is False
    assert plan.target_amps == 0.0


def test_import_cap_lowers_ramp_max():
    battery = BatteryConfig(nominal_voltage=50.0)
    gc = GridChargeConfig(max_grid_charge_a=60.0)
    reserve = ReserveTarget(
        target_soc=80.0,
        solar_bridge_soc=80.0,
        autonomy_floor_soc=20.0,
        rationale=Msg(key=""),
    )
    ctx = RampContext(
        telemetry=Telemetry(battery_soc=50.0, grid_present=True),
        forecast=ForecastBundle(),
        grid_stats=GridStats(remaining_window_minutes=15.0, currently_present=True),
        reserve=reserve,
        target_soc=80.0,
        blackout_risk=BlackoutRisk.HIGH,
        blackout_risk_score=0.8,
        battery=battery,
        grid_charge=gc,
        effective_max_charge_a=30.0,
    )
    plan = compute_ramp_plan(ctx)
    assert plan.max_amps == pytest.approx(30.0)
    if plan.enabled:
        assert plan.target_amps <= 30.0 + 1e-6
