"""HAEntityAdapter: implements InverterAdapter over Home Assistant entities.

Reads telemetry from sensor/binary_sensor entities and writes via number/
select/switch services, all driven by the capability->entity map in config.yaml.
"""

from __future__ import annotations

import logging
from typing import Any

from ..config import InverterConfig
from ..ha.client import HAClient
from ..ha.units import ha_numeric_from_any
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


def is_entity_on(domain: str, state: str | None) -> bool | None:
    """Whether an HA entity state represents 'on' for shed/restore semantics."""
    if state is None:
        return None
    s = str(state).strip().lower()
    if domain == "climate":
        if s in {"off", "unavailable", "unknown"}:
            return False
        return True
    if domain == "fan":
        if s in {"off", "unavailable", "unknown"}:
            return False
        return True
    return _to_bool(state)


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

        def state_dict(entity_id: str | None) -> Any:
            if not entity_id:
                return None
            return states.get(entity_id)

        def bool_val(entity_id: str | None) -> bool | None:
            st = state_dict(entity_id)
            if not st:
                return None
            return _to_bool(st.get("state"))

        self._last_successful_read_at = utcnow()
        return Telemetry(
            ts=self._last_successful_read_at,
            pv_power=ha_numeric_from_any(state_dict(self._read.pv_power), kind="power"),
            load_power=ha_numeric_from_any(state_dict(self._read.load_power), kind="power"),
            battery_soc=ha_numeric_from_any(state_dict(self._read.battery_soc), kind="soc"),
            battery_power=self._normalize_power(
                ha_numeric_from_any(state_dict(self._read.battery_power), kind="power")
            ),
            grid_power=ha_numeric_from_any(state_dict(self._read.grid_power), kind="power"),
            grid_present=bool_val(self._read.grid_present),
            battery_temp=ha_numeric_from_any(
                state_dict(self._read.battery_temp), kind="temperature"
            ),
        )

    def telemetry_from_cache(self) -> Telemetry:
        """Build telemetry from the live-stream cache (no network call)."""

        def state_dict(entity_id: str | None) -> Any:
            return self._cached_or_none(entity_id)

        def bool_val(entity_id: str | None) -> bool | None:
            st = state_dict(entity_id)
            if isinstance(st, dict):
                return _to_bool(st.get("state"))
            return _to_bool(st)

        return Telemetry(
            ts=self._last_successful_read_at or utcnow(),
            pv_power=ha_numeric_from_any(state_dict(self._read.pv_power), kind="power"),
            load_power=ha_numeric_from_any(state_dict(self._read.load_power), kind="power"),
            battery_soc=ha_numeric_from_any(state_dict(self._read.battery_soc), kind="soc"),
            battery_power=self._normalize_power(
                ha_numeric_from_any(state_dict(self._read.battery_power), kind="power")
            ),
            grid_power=ha_numeric_from_any(state_dict(self._read.grid_power), kind="power"),
            grid_present=bool_val(self._read.grid_present),
            battery_temp=ha_numeric_from_any(
                state_dict(self._read.battery_temp), kind="temperature"
            ),
        )

    def _write_entity(self, capability: Capability) -> str | None:
        return getattr(self._write, capability.value, None)

    def supports(self, capability: Capability) -> bool:
        return bool(self._write_entity(capability))

    async def read_capability(
        self, capability: Capability
    ) -> float | bool | None:
        entity_id = self._write_entity(capability)
        if not entity_id:
            return None
        st = await self._ha.get_state(entity_id)
        if st is None:
            return None
        raw = st.get("state")
        if capability is Capability.GRID_CHARGE_ENABLE:
            return _to_bool(raw)
        if capability is Capability.MAX_GRID_CHARGE_CURRENT:
            return ha_numeric_from_any(st, kind="current")
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
