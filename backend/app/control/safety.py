"""Safety layer: hard bounds, idempotency, and EEPROM write-rate limiting.

Every write is screened here before it reaches the inverter. This module is
deliberately conservative: when in doubt, it refuses to write.
"""

from __future__ import annotations

import logging
from datetime import datetime

from ..config import BatteryConfig, ControlConfig
from ..models import Capability, utcnow

log = logging.getLogger("control.safety")


class SafetyGuard:
    def __init__(self, battery: BatteryConfig, control: ControlConfig) -> None:
        self._battery = battery
        self._control = control
        # capability -> (last_write_ts, last_value)
        self._last_write: dict[Capability, tuple[datetime, object]] = {}

    def clamp(
        self, capability: Capability, value: float | bool | str
    ) -> tuple[float | bool | str, str | None]:
        """Clamp a value to its hardware-safe bounds. Returns (value, note)."""
        if capability is Capability.MAX_GRID_CHARGE_CURRENT:
            v = max(0.0, min(self._battery.max_grid_charge_a, float(value)))
            note = None if v == float(value) else "grid charge current clamped"
            return v, note
        if capability is Capability.GRID_CHARGE_ENABLE:
            return bool(value), None
        # WORK_MODE or others: pass through.
        return value, None

    def violates_hard_bounds(
        self, capability: Capability, value: float | bool | str
    ) -> str | None:
        """Return a reason string if the write must be REJECTED outright."""
        if not self._control.enforce_hard_bounds:
            return None
        return None

    def should_skip(
        self,
        capability: Capability,
        value: float | bool | str,
        current: float | bool | str | None,
        now: datetime | None = None,
    ) -> str | None:
        """Idempotency + EEPROM rate limiting. Returns skip reason or None."""
        now = now or utcnow()

        # Idempotency: skip if the inverter already holds the desired value.
        if current is not None and self._equal(capability, value, current):
            return "already set"

        last = self._last_write.get(capability)
        if last is not None:
            last_ts, last_val = last
            elapsed = (now - last_ts).total_seconds()
            if self._equal(capability, value, last_val):
                # We already commanded this recently; avoid re-writing.
                if elapsed < self._control.min_write_interval_seconds:
                    return "recently written (unchanged)"
            elif elapsed < self._control.min_write_interval_seconds:
                # Different value but too soon -> protect EEPROM.
                return (
                    f"rate-limited ({elapsed:.0f}s < "
                    f"{self._control.min_write_interval_seconds}s)"
                )
        return None

    def record_write(
        self, capability: Capability, value: float | bool | str, now: datetime | None = None
    ) -> None:
        self._last_write[capability] = (now or utcnow(), value)

    @staticmethod
    def _equal(
        capability: Capability,
        a: float | bool | str,
        b: float | bool | str,
    ) -> bool:
        if capability in (Capability.GRID_CHARGE_ENABLE,):
            return bool(a) == bool(b)
        if capability is Capability.WORK_MODE:
            return str(a) == str(b)
        try:
            return abs(float(a) - float(b)) < 0.5
        except (TypeError, ValueError):
            return str(a) == str(b)
