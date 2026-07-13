"""Collector: keeps a live cache, persists telemetry, tracks grid transitions.

Two responsibilities:
1. Consume the HA WebSocket state stream to keep the adapter cache hot and to
   detect grid on/off transitions the *instant* they happen (fires a callback
   so the reactive layer can grab an opportunistic top-up immediately).
2. Provide `sample()` for the scheduler to persist a telemetry row each cycle.

Grid transitions are stored as events for DISPLAY-ONLY statistics. They are
never used to predict the grid.
"""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Awaitable, Callable

from ..adapters.ha_entity import HAEntityAdapter
from ..ha.client import HAClient
from ..models import GridEvent, Telemetry
from ..storage import repo

log = logging.getLogger("ingest.collector")

GridChangeCallback = Callable[[bool], Awaitable[None]]


class Collector:
    def __init__(
        self,
        ha: HAClient,
        adapter: HAEntityAdapter,
        grid_present_entity: str | None,
        on_grid_change: GridChangeCallback | None = None,
        temp_entity: str | None = None,
    ) -> None:
        self._ha = ha
        self._adapter = adapter
        self._grid_entity = grid_present_entity
        self._temp_entity = temp_entity
        self._on_grid_change = on_grid_change
        self._last_grid_present: bool | None = None
        self._latest_temp: float | None = None
        self._latest: Telemetry | None = None
        self._grid_lock = asyncio.Lock()

    @property
    def latest(self) -> Telemetry | None:
        return self._latest

    def set_latest(self, telemetry: Telemetry) -> None:
        """Inject cached telemetry (demo / test helpers)."""
        self._latest = telemetry

    def set_grid_entity(self, entity_id: str | None) -> None:
        self._grid_entity = entity_id

    def set_temp_entity(self, entity_id: str | None) -> None:
        self._temp_entity = entity_id or None
        self._latest_temp = None

    def set_ha(self, ha) -> None:  # noqa: ANN001 - avoids import cycle
        self._ha = ha

    async def prime(self) -> None:
        """Load the last known grid state so we only log real transitions."""
        last = await repo.get_last_grid_event()
        if last is not None:
            self._last_grid_present = last.grid_present
        if self._temp_entity:
            try:
                st = await self._ha.get_state(self._temp_entity)
                if st:
                    from ..ha.units import ha_numeric_from_any

                    self._latest_temp = ha_numeric_from_any(st, kind="temperature")
            except Exception as e:  # noqa: BLE001
                log.debug("Initial outdoor temp read failed: %s", e)

    async def sample(self) -> Telemetry:
        """Read a fresh telemetry snapshot, persist it, and track grid state."""
        try:
            t = await self._adapter.read_telemetry()
        except Exception as e:  # noqa: BLE001 - resilience over strictness
            log.warning("Telemetry read failed: %s", e)
            # Fall back to whatever is in the cache.
            t = self._adapter.telemetry_from_cache()

        if self._temp_entity:
            if self._latest_temp is None:
                try:
                    st = await self._ha.get_state(self._temp_entity)
                    if st:
                        from ..ha.units import ha_numeric_from_any

                        self._latest_temp = ha_numeric_from_any(st, kind="temperature")
                except Exception as e:  # noqa: BLE001
                    log.debug("Outdoor temp REST read failed: %s", e)
            if self._latest_temp is not None:
                t.outdoor_temp = self._latest_temp

        self._latest = t
        await repo.save_telemetry(t)
        if t.grid_present is not None:
            await self._handle_grid_state(t.grid_present, notify=False)
        return t

    async def _handle_grid_state(self, present: bool, *, notify: bool = True) -> None:
        """Record grid transitions. Callback only from WS stream (not sample)."""
        should_notify = False
        async with self._grid_lock:
            if present == self._last_grid_present:
                return
            self._last_grid_present = present
            await repo.save_grid_event(GridEvent(grid_present=present))
            should_notify = notify
        log.info("Grid transition detected: grid_present=%s", present)
        if should_notify and self._on_grid_change is not None:
            try:
                await self._on_grid_change(present)
            except Exception as e:  # noqa: BLE001
                log.exception("on_grid_change callback failed: %s", e)

    async def run_stream(self) -> None:
        """Background task: keep the cache hot and react to grid transitions."""
        watched = self._adapter.watched_entities()
        async for data in self._ha.stream_states():
            entity_id = data.get("entity_id")
            new_state = data.get("new_state")
            if not entity_id or new_state is None:
                continue
            if entity_id in watched:
                self._adapter.update_cache(entity_id, new_state)
            if self._grid_entity and entity_id == self._grid_entity:
                from ..adapters.ha_entity import _to_bool  # local import

                present = _to_bool(new_state.get("state"))
                if present is not None:
                    await self._handle_grid_state(present)
            if self._temp_entity and entity_id == self._temp_entity:
                from ..ha.units import ha_numeric_from_any

                temp = ha_numeric_from_any(new_state, kind="temperature")
                if temp is not None:
                    self._latest_temp = temp

    async def run_stream_safe(self) -> None:
        """Keep the state stream alive; restart after unexpected exits.

        Uses exponential backoff with jitter (capped at 60s) so a persistently
        unreachable Home Assistant instance doesn't spin-loop the CPU/log, and
        so many restarting instances don't thunder back in lockstep.
        """
        backoff = 1.0
        max_backoff = 60.0
        while True:
            try:
                await self.run_stream()
                backoff = 1.0
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001
                from ..observability.metrics import metrics

                metrics.ha_ws_restarts += 1
                sleep_for = backoff * (0.5 + random.random() * 0.5)
                log.exception(
                    "State stream crashed: %s; restarting in %.1fs", e, sleep_for
                )
                await asyncio.sleep(sleep_for)
                backoff = min(backoff * 2, max_backoff)
