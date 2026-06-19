"""Tests for the safety guard (bounds, idempotency, rate limiting)."""

from __future__ import annotations

from datetime import timedelta

from app.config import BatteryConfig, ControlConfig
from app.control.safety import SafetyGuard
from app.models import Capability, utcnow


def _guard() -> SafetyGuard:
    battery = BatteryConfig(min_soc_floor=20.0, max_soc_ceiling=100.0, max_grid_charge_a=90.0)
    control = ControlConfig(min_write_interval_seconds=60, enforce_hard_bounds=True)
    return SafetyGuard(battery, control)


def test_clamp_grid_charge_current():
    g = _guard()
    v, note = g.clamp(Capability.MAX_GRID_CHARGE_CURRENT, 200.0)
    assert v == 90.0
    assert note is not None


def test_idempotency_skip_when_already_set():
    g = _guard()
    assert (
        g.should_skip(Capability.MAX_GRID_CHARGE_CURRENT, 40.0, current=40.0)
        == "already set"
    )


def test_rate_limit_blocks_rapid_change():
    g = _guard()
    now = utcnow()
    g.record_write(Capability.MAX_GRID_CHARGE_CURRENT, 50.0, now=now)
    skip = g.should_skip(
        Capability.MAX_GRID_CHARGE_CURRENT, 80.0, current=50.0, now=now + timedelta(seconds=5)
    )
    assert skip is not None and "rate-limited" in skip


def test_rate_limit_allows_after_interval():
    g = _guard()
    now = utcnow()
    g.record_write(Capability.MAX_GRID_CHARGE_CURRENT, 50.0, now=now)
    skip = g.should_skip(
        Capability.MAX_GRID_CHARGE_CURRENT, 80.0, current=50.0, now=now + timedelta(seconds=120)
    )
    assert skip is None
