"""Reactive grid logic and display-only statistics."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from ..config import BatteryConfig, GridChargeConfig, OptimizationPriority, ReserveConfig
from ..engine.priorities import resolve_weights
from ..grid.ramp import RampContext, compute_ramp_plan, legacy_plan
from ..models import (
    BlackoutRisk,
    Capability,
    ControlAction,
    ForecastBundle,
    GridChargePlan,
    GridEvent,
    GridStats,
    ReserveTarget,
    Telemetry,
    utcnow,
)
from ..storage import repo

log = logging.getLogger("grid.reactive")


@dataclass(frozen=True)
class GridChargeResult:
    actions: list[ControlAction]
    plan: GridChargePlan


class ReactiveGrid:
    def __init__(
        self,
        battery: BatteryConfig,
        reserve: ReserveConfig,
        grid_charge: GridChargeConfig | None = None,
        site_timezone: str = "auto",
    ) -> None:
        self._battery = battery
        self._reserve = reserve
        self._grid_charge = grid_charge or GridChargeConfig()
        self._site_timezone = site_timezone
        self._priority_weights = {
            k.value: v for k, v in resolve_weights().items()
        }

    def update_config(
        self,
        battery: BatteryConfig,
        reserve: ReserveConfig,
        grid_charge: GridChargeConfig | None = None,
        site_timezone: str | None = None,
        priority_order: list[OptimizationPriority] | None = None,
    ) -> None:
        self._battery = battery
        self._reserve = reserve
        if grid_charge is not None:
            self._grid_charge = grid_charge
        if site_timezone is not None:
            self._site_timezone = site_timezone
        if priority_order is not None:
            self._priority_weights = {
                k.value: v for k, v in resolve_weights(priority_order).items()
            }

    # --------------------------------------------------- opportunistic top-up --
    def opportunistic_actions(
        self,
        telemetry: Telemetry,
        target_soc: float,
        *,
        forecast: ForecastBundle | None = None,
        grid_stats: GridStats | None = None,
        reserve: ReserveTarget | None = None,
        blackout_risk: BlackoutRisk = BlackoutRisk.LOW,
        blackout_risk_score: float = 0.0,
        last_amps: float | None = None,
    ) -> GridChargeResult:
        """Grid charge on/off + target amps (ramp or legacy max-or-off)."""
        max_a = self._grid_charge.max_grid_charge_a

        if not self._grid_charge.ramp_enabled:
            return self._legacy_actions(telemetry, target_soc, max_a)

        ctx = RampContext(
            telemetry=telemetry,
            forecast=forecast,
            grid_stats=grid_stats,
            reserve=reserve
            or ReserveTarget(
                target_soc=target_soc,
                solar_bridge_soc=target_soc,
                autonomy_floor_soc=self._battery.min_soc_floor,
                rationale="",
            ),
            target_soc=target_soc,
            blackout_risk=blackout_risk,
            blackout_risk_score=blackout_risk_score,
            battery=self._battery,
            grid_charge=self._grid_charge,
            last_amps=last_amps,
            site_timezone=self._site_timezone,
            priority_weights=self._priority_weights,
        )
        plan = compute_ramp_plan(ctx)
        return self._plan_to_result(plan, telemetry, target_soc)

    def _legacy_actions(
        self, telemetry: Telemetry, target_soc: float, max_a: float
    ) -> GridChargeResult:
        actions: list[ControlAction] = []
        if not telemetry.grid_present:
            plan = legacy_plan(
                enabled=False,
                target_amps=0.0,
                max_amps=max_a,
                rationale="Grid absent; disable grid charge.",
            )
            actions.append(
                ControlAction(
                    capability=Capability.GRID_CHARGE_ENABLE,
                    value=False,
                    reason=plan.rationale,
                    priority=50,
                )
            )
            return GridChargeResult(actions=actions, plan=plan)

        soc = telemetry.battery_soc if telemetry.battery_soc is not None else 0.0
        if soc < target_soc:
            plan = legacy_plan(
                enabled=True,
                target_amps=max_a,
                max_amps=max_a,
                rationale=(
                    f"Grid present and SOC {soc:.0f}% < reserve target "
                    f"{target_soc:.0f}%: opportunistic top-up at max."
                ),
            )
            actions.append(
                ControlAction(
                    capability=Capability.GRID_CHARGE_ENABLE,
                    value=True,
                    reason=plan.rationale,
                    priority=100,
                )
            )
            actions.append(
                ControlAction(
                    capability=Capability.MAX_GRID_CHARGE_CURRENT,
                    value=max_a,
                    reason=f"Charge hard while grid available ({max_a:.0f} A).",
                    priority=90,
                )
            )
        else:
            plan = legacy_plan(
                enabled=False,
                target_amps=0.0,
                max_amps=max_a,
                rationale=(
                    f"Reserve target {target_soc:.0f}% met "
                    f"(SOC {soc:.0f}%); stop grid charge."
                ),
            )
            actions.append(
                ControlAction(
                    capability=Capability.GRID_CHARGE_ENABLE,
                    value=False,
                    reason=plan.rationale,
                    priority=80,
                )
            )
        return GridChargeResult(actions=actions, plan=plan)

    def _plan_to_result(
        self, plan: GridChargePlan, telemetry: Telemetry, target_soc: float
    ) -> GridChargeResult:
        actions: list[ControlAction] = []
        soc = telemetry.battery_soc if telemetry.battery_soc is not None else 0.0

        if plan.enabled:
            actions.append(
                ControlAction(
                    capability=Capability.GRID_CHARGE_ENABLE,
                    value=True,
                    reason=(
                        f"Grid present, SOC {soc:.0f}% < target {target_soc:.0f}%: "
                        f"ramp to {plan.target_amps:.0f} A."
                    ),
                    priority=100,
                )
            )
            actions.append(
                ControlAction(
                    capability=Capability.MAX_GRID_CHARGE_CURRENT,
                    value=plan.target_amps,
                    reason=plan.rationale,
                    priority=90,
                )
            )
        else:
            actions.append(
                ControlAction(
                    capability=Capability.GRID_CHARGE_ENABLE,
                    value=False,
                    reason=plan.rationale,
                    priority=80,
                )
            )
            if plan.target_amps > 0:
                actions.append(
                    ControlAction(
                        capability=Capability.MAX_GRID_CHARGE_CURRENT,
                        value=0.0,
                        reason=plan.rationale,
                        priority=70,
                    )
                )
        return GridChargeResult(actions=actions, plan=plan)

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
