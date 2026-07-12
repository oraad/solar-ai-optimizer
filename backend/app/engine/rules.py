"""Phase 2 rule-based decision engine (deterministic, explainable).

Core stance: the grid is assumed ABSENT for planning. We defend a conservative
reserve floor so the home survives even if the grid never returns. If the grid
does appear, the reactive layer exploits it immediately as a bonus.
"""

from __future__ import annotations

import logging
from collections.abc import Collection
from datetime import datetime, timedelta, timezone

from ..config import BatteryConfig, EngineConfig, GridChargeConfig, LoadSheddingConfig, OptimizationPriority, ReserveConfig
from ..grid.reactive import ReactiveGrid
from ..i18n import msg
from ..models import (
    BlackoutRisk,
    Capability,
    ControlAction,
    Decision,
    DecisionModifiers,
    ForecastBundle,
    GridChargePlan,
    GridStats,
    Msg,
    Override,
    ReserveSource,
    ReserveTarget,
    RiskBreakdown,
    Telemetry,
    utcnow,
)
from .explanation import build_explanation, build_inputs_digest
from .priorities import (
    DEFAULT_PRIORITY_ORDER,
    buffer_scale,
    effective_critical_w,
    autonomy_hours_scale,
    grid_present_risk_multiplier,
    resolve_weights,
    savings_buffer_relief,
)
from .shedding import LoadSheddingController

log = logging.getLogger("engine.rules")


class RuleEngine:
    def __init__(
        self,
        battery: BatteryConfig,
        reserve: ReserveConfig,
        engine_cfg: EngineConfig,
        reactive: ReactiveGrid,
        shedding: LoadSheddingConfig | None = None,
        grid_charge: GridChargeConfig | None = None,
    ) -> None:
        self._battery = battery
        self._reserve = reserve
        self._engine_cfg = engine_cfg
        self._reactive = reactive
        self._grid_charge = grid_charge or GridChargeConfig()
        self._shedding = LoadSheddingController(shedding or LoadSheddingConfig())
        self._total_kwp = 1.0
        self._last_grid_charge_amps: float | None = None
        self._weights = resolve_weights(engine_cfg.priority_order)
        self._prev_effective_critical_w: float | None = None
        self._last_adaptive_meta: dict[str, float | None] = {
            "effective_critical_w": None,
            "smoothed_load_w": None,
            "smoothed_discharge_w": None,
            "adaptive_blend_a": None,
        }

    def set_last_grid_charge_amps(self, amps: float | None) -> None:
        self._last_grid_charge_amps = amps

    def set_total_kwp(self, total_kwp: float) -> None:
        self._total_kwp = max(0.1, total_kwp)

    @property
    def last_effective_critical_w(self) -> float | None:
        return self._prev_effective_critical_w

    # --------------------------------------------------------- reserve floor --
    def compute_reserve(
        self,
        telemetry: Telemetry,
        forecast: ForecastBundle | None,
        *,
        smoothed_load_w: float | None = None,
        smoothed_discharge_w: float | None = None,
        update_hysteresis: bool = True,
    ) -> ReserveTarget:
        from .priorities import discharge_power_w

        cap_wh = self._battery.capacity_kwh * 1000.0
        w_r = self._weights[OptimizationPriority.resilience]
        w_s = self._weights[OptimizationPriority.savings]
        w_ss = self._weights[OptimizationPriority.self_sufficiency]
        adaptive_on = self._reserve.adaptive_load_enabled

        # Thin-history / unit-test fallback when caller didn't pass a mean.
        if adaptive_on and smoothed_load_w is None:
            load = (
                float(telemetry.load_power)
                if telemetry.load_power is not None
                else None
            )
            dis = discharge_power_w(telemetry.battery_power)
            if load is None and dis is None:
                pass
            elif load is None:
                smoothed_load_w = dis
                if smoothed_discharge_w is None:
                    smoothed_discharge_w = dis
            elif dis is None:
                smoothed_load_w = load
            else:
                smoothed_load_w = max(load, dis)
                if smoothed_discharge_w is None:
                    smoothed_discharge_w = dis

        leff, blend_a = effective_critical_w(
            critical_load_w=self._reserve.critical_load_w,
            smoothed_load_w=smoothed_load_w if adaptive_on else None,
            adaptive_enabled=adaptive_on,
            adaptive_cap_w=self._reserve.adaptive_load_cap_w,
            resilience_weight=w_r,
            savings_weight=w_s,
            self_sufficiency_weight=w_ss,
            prev_effective_w=self._prev_effective_critical_w,
        )
        if update_hysteresis:
            self._prev_effective_critical_w = leff

        # Explanation fields only when adaptive is on and a real signal was used.
        show_adaptive = adaptive_on and smoothed_load_w is not None
        meta_smooth = (
            round(smoothed_load_w, 1) if show_adaptive and smoothed_load_w is not None else None
        )
        meta_dis = (
            round(smoothed_discharge_w, 1)
            if show_adaptive and smoothed_discharge_w is not None
            else None
        )
        meta_blend = round(blend_a, 3) if show_adaptive else None
        meta_leff = round(leff, 1) if adaptive_on else None
        self._last_adaptive_meta = {
            "effective_critical_w": meta_leff,
            "smoothed_load_w": meta_smooth,
            "smoothed_discharge_w": meta_dis,
            "adaptive_blend_a": meta_blend,
        }

        # 1) Minimum autonomy floor: survive min_autonomy_hours of effective load.
        hours_eff = self._reserve.min_autonomy_hours * autonomy_hours_scale(w_r)
        autonomy_wh = leff * hours_eff
        autonomy_pct = 100.0 * autonomy_wh / cap_wh
        autonomy_floor_soc = max(self._battery.min_soc_floor, autonomy_pct)

        # 2) Solar-bridge: peak overnight cumulative deficit until solar recovers.
        bridge_wh = self._solar_bridge_wh(forecast, load_floor_w=leff)
        buffer = self._reserve.solar_bridge_buffer_pct
        degraded_note = ""
        if forecast and forecast.cloudy_tomorrow:
            buffer += self._reserve.cloudy_extra_buffer_pct
        if forecast and forecast.degraded:
            buffer += self._reserve.cloudy_extra_buffer_pct
            degraded_note = "degraded"
        buffer *= buffer_scale(w_r)
        buffer *= savings_buffer_relief(w_s)
        bridge_wh *= 1.0 + buffer / 100.0
        bridge_pct = 100.0 * bridge_wh / cap_wh
        solar_bridge_soc = min(
            self._battery.max_soc_ceiling,
            self._battery.min_soc_floor + bridge_pct,
        )

        target = min(
            self._battery.max_soc_ceiling,
            max(autonomy_floor_soc, solar_bridge_soc),
        )
        driver_label = (
            "engine.reserve.driver_solar_bridge"
            if solar_bridge_soc >= autonomy_floor_soc
            else "engine.reserve.driver_autonomy_floor"
        )
        extra_cold = ""
        extra_heat = ""
        extra_degraded = ""
        hdh = 0.0
        cdh = 0.0
        if forecast:
            hdh = forecast.heating_degree_hours_24h
            cdh = forecast.cooling_degree_hours_24h
            if hdh >= 5.0:
                extra_cold = "cold"
            elif cdh >= 5.0:
                extra_heat = "heat"
        if degraded_note:
            extra_degraded = "yes"
        rationale = msg(
            "engine.reserve.main",
            target=round(target, 0),
            driver=driver_label,
            autonomy=round(autonomy_floor_soc, 0),
            hours=round(hours_eff, 0),
            load=round(leff, 0),
            bridge=round(solar_bridge_soc, 0),
            bridge_kwh=round(bridge_wh / 1000, 1),
            buffer=round(buffer, 0),
            extra_cold=extra_cold,
            extra_heat=extra_heat,
            extra_degraded=extra_degraded,
            hdh=round(hdh, 0),
            cdh=round(cdh, 0),
        )
        return ReserveTarget(
            target_soc=round(target, 1),
            solar_bridge_soc=round(solar_bridge_soc, 1),
            autonomy_floor_soc=round(autonomy_floor_soc, 1),
            rationale=rationale,
            effective_critical_w=meta_leff if adaptive_on else round(leff, 1),
            smoothed_load_w=meta_smooth,
            smoothed_discharge_w=meta_dis,
            adaptive_blend_a=meta_blend if show_adaptive else (0.0 if not adaptive_on else None),
        )

    def _solar_bridge_wh(
        self, forecast: ForecastBundle | None, *, load_floor_w: float | None = None
    ) -> float:
        """Peak cumulative (load - solar) deficit over the next 24h, in Wh.

        This is the energy the battery must supply to carry loads through the
        dark hours until tomorrow's solar takes over.
        """
        floor = (
            load_floor_w
            if load_floor_w is not None
            else self._reserve.critical_load_w
        )
        if not forecast or not forecast.load:
            # No forecast yet: bridge effective critical load through a default night.
            return floor * 12.0

        solar_by_hour = {
            p.ts.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0): p.pv_power_w
            for p in forecast.solar
        }
        now = utcnow().replace(minute=0, second=0, microsecond=0)
        cum = 0.0
        peak = 0.0
        for i in range(24):
            ts = now + timedelta(hours=i)
            load_w = max(self._load_at(forecast, ts, load_floor_w=floor), floor)
            solar_w = solar_by_hour.get(ts, 0.0)
            net_deficit = max(0.0, load_w - solar_w)
            surplus = max(0.0, solar_w - load_w)
            cum += net_deficit
            cum -= surplus * self._battery.round_trip_efficiency
            cum = max(0.0, cum)
            peak = max(peak, cum)
        return peak

    def _load_at(
        self,
        forecast: ForecastBundle,
        ts: datetime,
        *,
        load_floor_w: float | None = None,
    ) -> float:
        fallback = (
            load_floor_w
            if load_floor_w is not None
            else self._reserve.critical_load_w
        )
        key = ts.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
        for p in forecast.load:
            if p.ts.astimezone(timezone.utc).replace(
                minute=0, second=0, microsecond=0
            ) == key:
                return p.load_power_w
        if not forecast.load:
            return fallback
        nearest = min(
            forecast.load,
            key=lambda p: abs(
                (
                    p.ts.astimezone(timezone.utc).replace(
                        minute=0, second=0, microsecond=0
                    )
                    - key
                ).total_seconds()
            ),
        )
        delta = abs(
            (
                nearest.ts.astimezone(timezone.utc).replace(
                    minute=0, second=0, microsecond=0
                )
                - key
            ).total_seconds()
        )
        if delta <= 3600:
            return nearest.load_power_w
        return fallback
    # ------------------------------------------------------------- decision --
    def decide(
        self,
        telemetry: Telemetry,
        forecast: ForecastBundle | None,
        grid_stats: GridStats | None,
        override: Override | None,
        shadow_mode: bool,
        telemetry_stale: bool = False,
        last_grid_charge_amps: float | None = None,
        *,
        plan_optimization: bool = True,
        plan_grid_charge: bool = True,
        plan_shedding: bool = True,
        pending_restore: Collection[str] | None = None,
        mpc_reserve: float | None = None,
        modifiers: DecisionModifiers | None = None,
        smoothed_load_w: float | None = None,
        smoothed_discharge_w: float | None = None,
        update_hysteresis: bool = True,
    ) -> Decision:
        risk_breakdown = RiskBreakdown()
        mpc_soc_applied: float | None = None
        rules_soc: float | None = None

        if plan_optimization:
            reserve = self.compute_reserve(
                telemetry,
                forecast,
                smoothed_load_w=smoothed_load_w,
                smoothed_discharge_w=smoothed_discharge_w,
                update_hysteresis=update_hysteresis,
            )
            rules_soc = reserve.target_soc
            target_soc = reserve.target_soc
            source = ReserveSource.RULES
            rationale = reserve.rationale

            if override and override.reserve_soc is not None:
                target_soc = max(
                    self._battery.min_soc_floor,
                    min(self._battery.max_soc_ceiling, override.reserve_soc),
                )
                source = ReserveSource.OPERATOR
                rationale = msg(
                    "engine.reserve.operator_pin",
                    target=round(target_soc, 0),
                    rules=round(rules_soc, 0),
                )
            elif mpc_reserve is not None:
                # MPC may not undercut the rules reserve floor.
                pinned = max(float(mpc_reserve), float(rules_soc))
                target_soc = max(
                    self._battery.min_soc_floor,
                    min(self._battery.max_soc_ceiling, pinned),
                )
                source = ReserveSource.MPC
                mpc_soc_applied = target_soc
                rationale = msg(
                    "engine.reserve.mpc_pin",
                    target=round(target_soc, 0),
                    rules=round(rules_soc, 0),
                )

            effective = ReserveTarget(
                target_soc=round(target_soc, 1),
                solar_bridge_soc=reserve.solar_bridge_soc,
                autonomy_floor_soc=reserve.autonomy_floor_soc,
                rationale=rationale,
                source=source,
                rules_soc=round(rules_soc, 1),
                effective_critical_w=reserve.effective_critical_w,
                smoothed_load_w=reserve.smoothed_load_w,
                smoothed_discharge_w=reserve.smoothed_discharge_w,
                adaptive_blend_a=reserve.adaptive_blend_a,
            )
            risk, score, risk_breakdown = self._blackout_risk(
                telemetry, effective, forecast, grid_stats
            )
            reserve = effective
        else:
            soc = telemetry.battery_soc or self._battery.min_soc_floor
            reserve = ReserveTarget(
                target_soc=soc,
                solar_bridge_soc=soc,
                autonomy_floor_soc=self._battery.min_soc_floor,
                rationale=msg("engine.reserve.optimization_disabled"),
                source=ReserveSource.RULES,
                rules_soc=soc,
            )
            target_soc = soc
            risk, score = BlackoutRisk.LOW, 0.0
            risk_breakdown = RiskBreakdown(score=0.0, label=BlackoutRisk.LOW)

        actions: list[ControlAction] = []
        advisories: list[Msg] = []
        grid_charge_plan: GridChargePlan | None = None
        gc_mode = ""
        max_a = self._reactive.effective_max_charge_a()

        last_amps = (
            last_grid_charge_amps
            if last_grid_charge_amps is not None
            else self._last_grid_charge_amps
        )

        if plan_grid_charge:
            if override and override.force_grid_charge:
                gc_mode = "override"
                grid_charge_plan = GridChargePlan(
                    enabled=True,
                    target_amps=max_a,
                    max_amps=max_a,
                    rationale=msg("engine.override.force_grid_charge_plan"),
                )
                actions.append(
                    ControlAction(
                        capability=Capability.GRID_CHARGE_ENABLE,
                        value=True,
                        reason=msg("engine.override.force_grid_charge"),
                        priority=120,
                    )
                )
                actions.append(
                    ControlAction(
                        capability=Capability.MAX_GRID_CHARGE_CURRENT,
                        value=max_a,
                        reason=grid_charge_plan.rationale,
                        priority=110,
                    )
                )
            elif override and override.force_grid_charge is False:
                gc_mode = "override"
                grid_charge_plan = GridChargePlan(
                    enabled=False,
                    target_amps=0.0,
                    max_amps=max_a,
                    rationale=msg("engine.override.disable_grid_charge_plan"),
                )
                actions.append(
                    ControlAction(
                        capability=Capability.GRID_CHARGE_ENABLE,
                        value=False,
                        reason=msg("engine.override.disable_grid_charge"),
                        priority=120,
                    )
                )
                actions.append(
                    ControlAction(
                        capability=Capability.MAX_GRID_CHARGE_CURRENT,
                        value=0.0,
                        reason=msg("engine.override.grid_charge_zero"),
                        priority=110,
                    )
                )
            elif telemetry_stale:
                gc_mode = "stale"
                grid_charge_plan, stale_actions = self._conservative_grid_charge_off(
                    max_a,
                    msg("engine.grid.telemetry_stale"),
                )
                actions.extend(stale_actions)
            else:
                result = self._reactive.opportunistic_actions(
                    telemetry,
                    target_soc,
                    forecast=forecast,
                    grid_stats=grid_stats,
                    reserve=reserve,
                    blackout_risk=risk,
                    blackout_risk_score=score,
                    last_amps=last_amps,
                )
                actions.extend(result.actions)
                grid_charge_plan = result.plan
                gc_mode = "ramp" if grid_charge_plan and grid_charge_plan.cap_chain else "legacy"

        if plan_optimization:
            soc = telemetry.battery_soc or 0.0
            pv = telemetry.pv_power or 0.0
            load = telemetry.load_power or 0.0
            if soc >= min(99.0, self._battery.max_soc_ceiling - 1) and pv > load:
                advisories.append(
                    msg(
                        "engine.advisory.surplus",
                        kw=round((pv - load) / 1000, 1),
                    )
                )

            summary = self._summary(
                telemetry, reserve, target_soc, risk, self._engine_cfg.priority_order
            )
        else:
            summary = msg("engine.summary.shedding_only")

        if advisories:
            a = advisories[0]
            summary = Msg(
                key=summary.key,
                params={
                    **summary.params,
                    "advisory_suffix": "surplus",
                    "advisory_kw": a.params.get("kw", 0),
                },
            )

        if plan_shedding and override and override.force_shed_off:
            shed_actions = self._shedding.force_off_plan()
        elif plan_shedding:
            shed_actions = self._shedding.plan(
                telemetry,
                telemetry_stale=telemetry_stale,
                pending_restore=pending_restore,
            )
        else:
            shed_actions = []

        mods = modifiers or DecisionModifiers(shadow=shadow_mode)
        explanation = build_explanation(
            reserve=reserve,
            risk=risk_breakdown,
            grid_charge=grid_charge_plan,
            shed_count=len(shed_actions),
            modifiers=mods,
            inputs_digest=build_inputs_digest(
                telemetry,
                forecast,
                telemetry_stale=telemetry_stale,
                plan_optimization=plan_optimization,
                plan_grid_charge=plan_grid_charge,
                plan_shedding=plan_shedding,
            ),
            mpc_soc=mpc_soc_applied,
            gc_mode=gc_mode,
        )

        return Decision(
            ts=utcnow(),
            reserve=reserve,
            actions=sorted(actions, key=lambda a: a.priority, reverse=True),
            shed_actions=shed_actions,
            blackout_risk=risk,
            blackout_risk_score=round(score, 3),
            summary=summary,
            shadow_mode=shadow_mode,
            grid_charge=grid_charge_plan,
            explanation=explanation,
        )

    @staticmethod
    def _conservative_grid_charge_off(
        max_a: float, rationale: Msg
    ) -> tuple[GridChargePlan, list[ControlAction]]:
        plan = GridChargePlan(
            enabled=False,
            target_amps=0.0,
            max_amps=max_a,
            rationale=rationale,
        )
        actions = [
            ControlAction(
                capability=Capability.GRID_CHARGE_ENABLE,
                value=False,
                reason=rationale,
                priority=120,
            ),
            ControlAction(
                capability=Capability.MAX_GRID_CHARGE_CURRENT,
                value=0.0,
                reason=msg("engine.grid.grid_charge_zero_conservative"),
                priority=110,
            ),
        ]
        return plan, actions

    def _blackout_risk(
        self,
        telemetry: Telemetry,
        reserve: ReserveTarget,
        forecast: ForecastBundle | None,
        grid_stats: GridStats | None = None,
    ) -> tuple[BlackoutRisk, float, RiskBreakdown]:
        soc = telemetry.battery_soc
        if soc is None:
            return (
                BlackoutRisk.MODERATE,
                0.5,
                RiskBreakdown(score=0.5, label=BlackoutRisk.MODERATE),
            )

        if soc <= self._battery.min_soc_floor:
            return (
                BlackoutRisk.CRITICAL,
                1.0,
                RiskBreakdown(score=1.0, label=BlackoutRisk.CRITICAL, floor_clamped=True),
            )

        target = max(reserve.target_soc, 1.0)
        deficit_ratio = max(0.0, min(1.0, (target - soc) / target))

        from ..forecast.helpers import expected_clear_sky_kwh

        expected_clear = expected_clear_sky_kwh(self._total_kwp)
        tomorrow_kwh: float | None = None
        if forecast:
            tomorrow_kwh = forecast.solar_tomorrow_kwh
            solar_factor = 1.0 - max(
                0.0, min(1.0, tomorrow_kwh / expected_clear)
            )
        else:
            solar_factor = 0.5

        score = 0.6 * deficit_ratio + 0.4 * solar_factor
        grid_mult: float | None = None
        if telemetry.grid_present:
            grid_mult = grid_present_risk_multiplier(
                self._weights[OptimizationPriority.resilience],
                self._weights[OptimizationPriority.savings],
                present_elapsed_minutes=(
                    grid_stats.present_elapsed_minutes if grid_stats else None
                ),
                remaining_window_minutes=(
                    grid_stats.remaining_window_minutes if grid_stats else None
                ),
            )
            score *= grid_mult

        floor_clamped = False
        if soc <= reserve.autonomy_floor_soc:
            score = max(score, 0.7)
            floor_clamped = True

        if score < 0.25:
            risk = BlackoutRisk.LOW
        elif score < 0.5:
            risk = BlackoutRisk.MODERATE
        elif score < 0.75:
            risk = BlackoutRisk.HIGH
        else:
            risk = BlackoutRisk.CRITICAL
        breakdown = RiskBreakdown(
            score=round(score, 3),
            label=risk,
            deficit_ratio=round(deficit_ratio, 3),
            solar_factor=round(solar_factor, 3),
            tomorrow_kwh=tomorrow_kwh,
            clear_sky_kwh=round(expected_clear, 2),
            grid_multiplier=grid_mult,
            floor_clamped=floor_clamped,
        )
        return risk, score, breakdown

    @staticmethod
    def _summary(
        telemetry: Telemetry,
        reserve: ReserveTarget,
        target_soc: float,
        risk: BlackoutRisk,
        priority_order: list,
    ) -> Msg:
        soc = telemetry.battery_soc
        soc_str = f"{soc:.0f}" if soc is not None else "?"
        key = (
            "engine.summary.with_priorities_present"
            if telemetry.grid_present
            else "engine.summary.with_priorities_absent"
        )
        seq = priority_order or DEFAULT_PRIORITY_ORDER
        return msg(
            key,
            order=",".join(p.value for p in seq),
            soc=soc_str,
            target=round(target_soc, 0),
            risk=risk.value,
            extra="",
            advisory_suffix="",
            advisory_kw=0,
            prefix="",
        )
