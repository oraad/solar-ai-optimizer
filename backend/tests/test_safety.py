"""Tests for the safety guard (bounds, idempotency, rate limiting)."""

from __future__ import annotations

from datetime import timedelta

from app.config import BatteryConfig, ControlConfig, GridChargeConfig
from app.control.safety import SafetyGuard
from app.i18n.skip_keys import REJECT_EXCEEDS_MAX_GRID_CHARGE, SKIP_ALREADY_SET, SKIP_RATE_LIMITED
from app.models import Capability, utcnow


def _guard() -> SafetyGuard:
    battery = BatteryConfig(min_soc_floor=20.0, max_soc_ceiling=100.0)
    grid_charge = GridChargeConfig(max_grid_charge_a=90.0)
    control = ControlConfig(min_write_interval_seconds=60, enforce_hard_bounds=True)
    return SafetyGuard(battery, control, grid_charge)


def test_clamp_grid_charge_current():
    g = _guard()
    v, note = g.clamp(Capability.MAX_GRID_CHARGE_CURRENT, 200.0)
    assert v == 90.0
    assert note is not None


def test_idempotency_skip_when_already_set():
    g = _guard()
    assert (
        g.should_skip(Capability.MAX_GRID_CHARGE_CURRENT, 40.0, current=40.0)
        == SKIP_ALREADY_SET
    )


def test_rate_limit_blocks_rapid_change():
    g = _guard()
    now = utcnow()
    g.record_write(Capability.MAX_GRID_CHARGE_CURRENT, 50.0, now=now)
    skip = g.should_skip(
        Capability.MAX_GRID_CHARGE_CURRENT, 80.0, current=50.0, now=now + timedelta(seconds=5)
    )
    assert skip == SKIP_RATE_LIMITED or (
        skip is not None and SKIP_RATE_LIMITED in skip
    )


def test_rate_limit_allows_after_interval():
    g = _guard()
    now = utcnow()
    g.record_write(Capability.MAX_GRID_CHARGE_CURRENT, 50.0, now=now)
    skip = g.should_skip(
        Capability.MAX_GRID_CHARGE_CURRENT, 80.0, current=50.0, now=now + timedelta(seconds=120)
    )
    assert skip is None


def test_hard_bounds_rejects_over_max():
    g = _guard()
    reason = g.violates_hard_bounds(Capability.MAX_GRID_CHARGE_CURRENT, 200.0)
    assert reason is not None
    assert REJECT_EXCEEDS_MAX_GRID_CHARGE in reason


def test_hard_bounds_rejects_negative():
    g = _guard()
    reason = g.violates_hard_bounds(Capability.MAX_GRID_CHARGE_CURRENT, -5.0)
    assert reason is not None


def test_hard_bounds_disabled_allows_clamp_path():
    battery = BatteryConfig(min_soc_floor=20.0, max_soc_ceiling=100.0)
    grid_charge = GridChargeConfig(max_grid_charge_a=90.0)
    control = ControlConfig(min_write_interval_seconds=60, enforce_hard_bounds=False)
    g = SafetyGuard(battery, control, grid_charge)
    assert g.violates_hard_bounds(Capability.MAX_GRID_CHARGE_CURRENT, 200.0) is None
