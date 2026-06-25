"""Safety layer: hard bounds, idempotency, and EEPROM write-rate limiting.

Every write is screened here before it reaches the inverter. This module is
deliberately conservative: when in doubt, it refuses to write.
"""

from __future__ import annotations

import logging
from datetime import datetime

from ..config import BatteryConfig, ControlConfig, GridChargeConfig
from ..i18n.skip_keys import (
    REJECT_EXCEEDS_MAX_GRID_CHARGE,
    REJECT_NEGATIVE_GRID_CHARGE,
    SKIP_ALREADY_SET,
    SKIP_RATE_LIMITED,
    SKIP_RECENTLY_WRITTEN,
    skip_key,
)
from ..models import Capability, utcnow

log = logging.getLogger("control.safety")


class SafetyGuard:
    def __init__(
        self,
        battery: BatteryConfig,
        control: ControlConfig,
        grid_charge: GridChargeConfig | None = None,
    ) -> None:
        self._battery = battery
        self._control = control
        self._grid_charge = grid_charge or GridChargeConfig()
        # capability -> (last_write_ts, last_value)
        self._last_write: dict[Capability, tuple[datetime, object]] = {}

    def clamp(
        self, capability: Capability, value: float | bool
    ) -> tuple[float | bool, str | None]:
        """Clamp a value to its hardware-safe bounds. Returns (value, note)."""
        if capability is Capability.MAX_GRID_CHARGE_CURRENT:
            v = max(0.0, min(self._grid_charge.max_grid_charge_a, float(value)))
            note = None if v == float(value) else "grid charge current clamped"
            return v, note
        if capability is Capability.GRID_CHARGE_ENABLE:
            return bool(value), None
        return value, None

    def violates_hard_bounds(
        self, capability: Capability, value: float | bool
    ) -> str | None:
        """Return a skip/reject key if the write must be REJECTED outright."""
        if not self._control.enforce_hard_bounds:
            return None
        if capability is Capability.MAX_GRID_CHARGE_CURRENT:
            amps = float(value)
            if amps < 0:
                return REJECT_NEGATIVE_GRID_CHARGE
            if amps > self._grid_charge.max_grid_charge_a:
                return skip_key(
                    REJECT_EXCEEDS_MAX_GRID_CHARGE,
                    max=self._grid_charge.max_grid_charge_a,
                )
        return None

    def should_skip(
        self,
        capability: Capability,
        value: float | bool,
        current: float | bool | None,
        now: datetime | None = None,
    ) -> str | None:
        """Idempotency + EEPROM rate limiting. Returns skip reason key or None."""
        now = now or utcnow()

        # Idempotency: skip if the inverter already holds the desired value.
        if current is not None and self._equal(capability, value, current):
            return SKIP_ALREADY_SET

        last = self._last_write.get(capability)
        if last is not None:
            last_ts, last_val = last
            elapsed = (now - last_ts).total_seconds()
            if self._equal(capability, value, last_val):
                # We already commanded this recently; avoid re-writing.
                if elapsed < self._control.min_write_interval_seconds:
                    return SKIP_RECENTLY_WRITTEN
            elif elapsed < self._control.min_write_interval_seconds:
                # Different value but too soon -> protect EEPROM.
                return skip_key(
                    SKIP_RATE_LIMITED,
                    elapsed=int(elapsed),
                    min=self._control.min_write_interval_seconds,
                )
        return None

    def record_write(
        self, capability: Capability, value: float | bool, now: datetime | None = None
    ) -> None:
        self._last_write[capability] = (now or utcnow(), value)

    @staticmethod
    def _equal(
        capability: Capability,
        a: float | bool,
        b: float | bool,
    ) -> bool:
        if capability is Capability.GRID_CHARGE_ENABLE:
            return bool(a) == bool(b)
        return abs(float(a) - float(b)) < 0.5
