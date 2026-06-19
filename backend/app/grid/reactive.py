"""Reactive grid logic and display-only statistics."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from ..config import BatteryConfig, ReserveConfig
from ..models import (
    Capability,
    ControlAction,
    GridEvent,
    GridStats,
    Telemetry,
    utcnow,
)
from ..storage import repo

log = logging.getLogger("grid.reactive")


class ReactiveGrid:
    def __init__(self, battery: BatteryConfig, reserve: ReserveConfig) -> None:
        self._battery = battery
        self._reserve = reserve

    # --------------------------------------------------- opportunistic top-up --
    def opportunistic_actions(
        self, telemetry: Telemetry, target_soc: float
    ) -> list[ControlAction]:
        """If the grid is physically present and we are below the reserve target,
        grab it: enable grid charge at max safe current. Windows are short and
        unpredictable, so when grid exists we charge hard. No prediction involved.
        """
        actions: list[ControlAction] = []
        if not telemetry.grid_present:
            # Grid absent: ensure grid charge is off (don't rely on a grid that
            # isn't there; also avoids surprise draw if it flickers on).
            actions.append(
                ControlAction(
                    capability=Capability.GRID_CHARGE_ENABLE,
                    value=False,
                    reason="Grid absent; disable grid charge.",
                    priority=50,
                )
            )
            return actions

        soc = telemetry.battery_soc if telemetry.battery_soc is not None else 0.0
        if soc < target_soc:
            amps = self._battery.max_grid_charge_a
            actions.append(
                ControlAction(
                    capability=Capability.GRID_CHARGE_ENABLE,
                    value=True,
                    reason=(
                        f"Grid present and SOC {soc:.0f}% < reserve target "
                        f"{target_soc:.0f}%: opportunistic top-up."
                    ),
                    priority=100,
                )
            )
            actions.append(
                ControlAction(
                    capability=Capability.MAX_GRID_CHARGE_CURRENT,
                    value=amps,
                    reason=f"Charge hard while grid available ({amps:.0f} A).",
                    priority=90,
                )
            )
        else:
            actions.append(
                ControlAction(
                    capability=Capability.GRID_CHARGE_ENABLE,
                    value=False,
                    reason=(
                        f"Reserve target {target_soc:.0f}% met "
                        f"(SOC {soc:.0f}%); stop grid charge."
                    ),
                    priority=80,
                )
            )
        return actions

    # ---------------------------------------------------------------- stats --
    async def compute_stats(
        self, now: datetime | None = None, live_present: bool | None = None
    ) -> GridStats:
        now = now or utcnow()
        window_7d = now - timedelta(days=7)
        window_24h = now - timedelta(hours=24)

        events = await repo.get_grid_events_since(window_7d)
        # Determine the state at the start of the 7d window.
        initial_present = await self._state_at(window_7d)

        uptime_24h = self._uptime_pct(events, window_24h, now, await self._state_at(window_24h))
        uptime_7d = self._uptime_pct(events, window_7d, now, initial_present)
        avg_window = self._avg_present_window_minutes(events, window_7d, now, initial_present)
        transitions_24h = sum(1 for e in events if e.ts >= window_24h)

        last = await repo.get_last_grid_event()
        currently = (
            live_present
            if live_present is not None
            else (last.grid_present if last else initial_present)
        )
        last_seen = await self._last_present_time(
            events, initial_present, window_7d, currently_present=currently, now=now
        )

        return GridStats(
            uptime_pct_24h=round(uptime_24h, 1),
            uptime_pct_7d=round(uptime_7d, 1),
            avg_window_minutes=round(avg_window, 1),
            last_seen=last_seen,
            currently_present=currently,
            transitions_24h=transitions_24h,
        )

    async def _state_at(self, when: datetime) -> bool:
        """Best-effort grid state just before `when` (default off)."""
        # Look back further for the last event preceding the window.
        events = await repo.get_grid_events_since(when - timedelta(days=30))
        prior = [e for e in events if e.ts <= when]
        if prior:
            return prior[-1].grid_present
        return False

    def _intervals(
        self,
        events: list[GridEvent],
        start: datetime,
        end: datetime,
        initial_present: bool,
    ) -> list[tuple[datetime, datetime, bool]]:
        """Build (start, end, present) intervals across [start, end]."""
        relevant = [e for e in events if start <= e.ts <= end]
        intervals: list[tuple[datetime, datetime, bool]] = []
        cursor = start
        present = initial_present
        for e in relevant:
            if e.ts > cursor:
                intervals.append((cursor, e.ts, present))
            present = e.grid_present
            cursor = e.ts
        if cursor < end:
            intervals.append((cursor, end, present))
        return intervals

    def _uptime_pct(
        self,
        events: list[GridEvent],
        start: datetime,
        end: datetime,
        initial_present: bool,
    ) -> float:
        total = (end - start).total_seconds()
        if total <= 0:
            return 0.0
        up = sum(
            (b - a).total_seconds()
            for a, b, present in self._intervals(events, start, end, initial_present)
            if present
        )
        return 100.0 * up / total

    def _avg_present_window_minutes(
        self,
        events: list[GridEvent],
        start: datetime,
        end: datetime,
        initial_present: bool,
    ) -> float:
        present_intervals = [
            (b - a).total_seconds() / 60.0
            for a, b, present in self._intervals(events, start, end, initial_present)
            if present
        ]
        if not present_intervals:
            return 0.0
        return sum(present_intervals) / len(present_intervals)

    async def _last_present_time(
        self,
        events: list[GridEvent],
        initial_present: bool,
        start: datetime,
        *,
        currently_present: bool | None = None,
        now: datetime | None = None,
    ) -> datetime | None:
        if currently_present:
            return now or utcnow()
        present_events = [e for e in events if e.grid_present]
        if present_events:
            return present_events[-1].ts
        if initial_present:
            return start
        return None
