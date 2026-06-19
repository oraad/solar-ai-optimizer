"""HAEntityAdapter: implements InverterAdapter over Home Assistant entities.

Reads telemetry from sensor/binary_sensor entities and writes via number/
select/switch services, all driven by the capability->entity map in config.yaml.
"""

from __future__ import annotations

import logging
from typing import Any

from ..config import InverterConfig
from ..ha.client import HAClient
from datetime import datetime

from ..models import Capability, Telemetry, utcnow
from .base import InverterAdapter

log = logging.getLogger("adapters.ha")

_ON_VALUES = {"on", "true", "1", "home", "connected", "present"}
_OFF_VALUES = {"off", "false", "0", "away", "disconnected", "absent"}


def _to_float(raw: Any) -> float | None:
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _to_bool(raw: Any) -> bool | None:
    if raw is None:
        return None
    s = str(raw).strip().lower()
    if s in _ON_VALUES:
        return True
    if s in _OFF_VALUES:
        return False
    return None


class HAEntityAdapter(InverterAdapter):
    def __init__(self, ha: HAClient, cfg: InverterConfig) -> None:
        self._ha = ha
        self._cfg = cfg
        self._read = cfg.read
        self._write = cfg.write
        # Latest entity states cache, fed by the live stream for fast reads.
        self._cache: dict[str, Any] = {}
        self._last_successful_read_at: datetime | None = None

    def update_config(self, cfg: InverterConfig) -> None:
        """Swap the entity map (e.g. after a UI config change), keeping the cache."""
        self._cfg = cfg
        self._read = cfg.read
        self._write = cfg.write

    def set_ha(self, ha: HAClient) -> None:
        """Swap the HA client (e.g. after the connection is reconfigured)."""
        self._ha = ha

    # ---------------------------------------------------------------- cache --
    def update_cache(self, entity_id: str, state: Any) -> None:
        self._cache[entity_id] = state

    def _cached_or_none(self, entity_id: str | None) -> Any:
        if not entity_id:
            return None
        return self._cache.get(entity_id)

    def _normalize_power(self, watts: float | None) -> float | None:
        if watts is None or not self._cfg.invert_battery_power:
            return watts
        return -watts

    def watched_entities(self) -> set[str]:
        """All read entities we care about for the live stream."""
        return {
            e
            for e in [
                self._read.pv_power,
                self._read.load_power,
                self._read.battery_soc,
                self._read.battery_power,
                self._read.grid_power,
                self._read.grid_present,
                self._read.battery_temp,
            ]
            if e
        }

    # ----------------------------------------------------------------- read --
    async def read_telemetry(self) -> Telemetry:
        """Read all mapped sensors via REST (authoritative snapshot)."""
        states = {s["entity_id"]: s for s in await self._ha.get_states()}
        # refresh cache too
        for eid, st in states.items():
            self._cache[eid] = st

        def val(entity_id: str | None) -> Any:
            if not entity_id:
                return None
            st = states.get(entity_id)
            return st.get("state") if st else None

        self._last_successful_read_at = utcnow()
        return Telemetry(
            ts=self._last_successful_read_at,
            pv_power=_to_float(val(self._read.pv_power)),
            load_power=_to_float(val(self._read.load_power)),
            battery_soc=_to_float(val(self._read.battery_soc)),
            battery_power=self._normalize_power(_to_float(val(self._read.battery_power))),
            grid_power=_to_float(val(self._read.grid_power)),
            grid_present=_to_bool(val(self._read.grid_present)),
            battery_temp=_to_float(val(self._read.battery_temp)),
        )

    def telemetry_from_cache(self) -> Telemetry:
        """Build telemetry from the live-stream cache (no network call)."""

        def state(entity_id: str | None) -> Any:
            st = self._cached_or_none(entity_id)
            if isinstance(st, dict):
                return st.get("state")
            return st

        return Telemetry(
            ts=self._last_successful_read_at or utcnow(),
            pv_power=_to_float(state(self._read.pv_power)),
            load_power=_to_float(state(self._read.load_power)),
            battery_soc=_to_float(state(self._read.battery_soc)),
            battery_power=self._normalize_power(_to_float(state(self._read.battery_power))),
            grid_power=_to_float(state(self._read.grid_power)),
            grid_present=_to_bool(state(self._read.grid_present)),
            battery_temp=_to_float(state(self._read.battery_temp)),
        )

    def _write_entity(self, capability: Capability) -> str | None:
        return getattr(self._write, capability.value, None)

    def supports(self, capability: Capability) -> bool:
        return bool(self._write_entity(capability))

    async def read_capability(
        self, capability: Capability
    ) -> float | bool | str | None:
        entity_id = self._write_entity(capability)
        if not entity_id:
            return None
        st = await self._ha.get_state(entity_id)
        if st is None:
            return None
        raw = st.get("state")
        if capability is Capability.GRID_CHARGE_ENABLE:
            return _to_bool(raw)
        if capability is Capability.WORK_MODE:
            return raw
        return _to_float(raw)

    # ---------------------------------------------------------------- write --
    async def set_grid_charge(self, enabled: bool) -> None:
        entity_id = self._write.grid_charge_enable
        if not entity_id:
            raise RuntimeError("grid_charge_enable not mapped")
        await self._ha.toggle_entity(entity_id, enabled)

    async def set_max_grid_charge_current(self, amps: float) -> None:
        entity_id = self._write.max_grid_charge_current
        if not entity_id:
            raise RuntimeError("max_grid_charge_current not mapped")
        await self._ha.set_number(entity_id, amps)

    async def set_work_mode(self, mode: str) -> None:
        entity_id = self._write.work_mode
        if not entity_id:
            raise RuntimeError("work_mode not mapped")
        # Map logical mode key -> HA option label if provided.
        option = self._cfg.work_modes.get(mode, mode)
        await self._ha.select_option(entity_id, option)
