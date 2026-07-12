"""Phase 3 (optional): Model Predictive Control optimizer.

Solves a linear program over a rolling horizon to plan battery dispatch under
the worst-case assumption that the GRID IS ABSENT for the whole horizon (the
core resilience stance). The objective is weighted resilience >> self-sufficiency
>> cost (cost ~0 under a flat tariff).

This module requires PuLP. If PuLP is not installed, importing/constructing
`MPCEngine` raises, and the orchestrator transparently falls back to the rule
engine. Each cycle we re-solve and apply only the first action.
"""

from __future__ import annotations

import logging
from collections.abc import Collection
from datetime import timedelta, timezone

# Hard dependency for this optional engine. ImportError -> fallback to rules.
import pulp  # noqa: F401

from ..config import (
    BatteryConfig,
    EngineConfig,
    GridChargeConfig,
    LoadSheddingConfig,
    OptimizationPriority,
    ReserveConfig,
)
from ..grid.reactive import ReactiveGrid
from ..models import (
    BlackoutRisk,
    Decision,
    DecisionModifiers,
    ForecastBundle,
    GridStats,
    Msg,
    Override,
    Telemetry,
    utcnow,
)
from .rules import RuleEngine
from .priorities import (
    buffer_scale,
    effective_critical_w,
    mpc_weights,
    resolve_weights,
    savings_buffer_relief,
)

log = logging.getLogger("engine.mpc")


class MPCEngine:
    def __init__(
        self,
        battery: BatteryConfig,
        reserve: ReserveConfig,
        engine_cfg: EngineConfig,
        shedding: LoadSheddingConfig | None = None,
        grid_charge: GridChargeConfig | None = None,
        total_kwp: float = 1.0,
        rule_engine: RuleEngine | None = None,
    ) -> None:
        self._battery = battery
        self._reserve = reserve
        self._engine_cfg = engine_cfg
        self._shedding = shedding or LoadSheddingConfig()
        self._grid_charge = grid_charge or GridChargeConfig()
        self._total_kwp = total_kwp
        self._rule: RuleEngine | None = rule_engine
        self._weights = resolve_weights(engine_cfg.priority_order)
        self._site_import_w: float | None = None

    def set_site_import_w(self, watts: float | None) -> None:
        self._site_import_w = watts

    def _effective_max_charge_a(self) -> float:
        from ..ha.units import effective_max_grid_charge_a

        return effective_max_grid_charge_a(
            max_grid_charge_a=self._grid_charge.max_grid_charge_a,
            nominal_voltage=self._battery.nominal_voltage,
            site_import_w=self._site_import_w,
        )

    def _rule_engine(self, reactive: ReactiveGrid) -> RuleEngine:
        if self._rule is None:
            self._rule = RuleEngine(
                self._battery,
                self._reserve,
                self._engine_cfg,
                reactive,
                self._shedding,
                self._grid_charge,
            )
        self._rule.set_total_kwp(self._total_kwp)
        return self._rule

    def decide(
        self,
        telemetry: Telemetry,
        forecast: ForecastBundle | None,
        grid_stats: GridStats | None,
        override: Override | None,
        shadow_mode: bool,
        reactive: ReactiveGrid,
        telemetry_stale: bool = False,
        last_grid_charge_amps: float | None = None,
        *,
        plan_optimization: bool = True,
        plan_grid_charge: bool = True,
        plan_shedding: bool = True,
        pending_restore: Collection[str] | None = None,
        modifiers: DecisionModifiers | None = None,
        smoothed_load_w: float | None = None,
        smoothed_discharge_w: float | None = None,
        update_hysteresis: bool = True,
    ) -> Decision:
        # Build the action set with the rule engine; pass MPC reserve explicitly
        # (never fake it as an operator override.reserve_soc).
        rule = self._rule_engine(reactive)

        mpc_reserve, unserved_wh, feasible = self._solve(
            telemetry, forecast, smoothed_load_w=smoothed_load_w, rule=rule
        )

        pin: float | None = None
        if plan_optimization and mpc_reserve is not None:
            if override is None or override.reserve_soc is None:
                pin = mpc_reserve

        decision = rule.decide(
            telemetry,
            forecast,
            grid_stats,
            override,
            shadow_mode,
            telemetry_stale=telemetry_stale,
            last_grid_charge_amps=last_grid_charge_amps,
            plan_optimization=plan_optimization,
            plan_grid_charge=plan_grid_charge,
            plan_shedding=plan_shedding,
            pending_restore=pending_restore,
            mpc_reserve=pin,
            modifiers=modifiers,
            smoothed_load_w=smoothed_load_w,
            smoothed_discharge_w=smoothed_discharge_w,
            update_hysteresis=update_hysteresis,
        )

        # Enrich risk + summary with MPC survivability result.
        # Missing forecast / no pin: leave rules risk intact (do not force CRITICAL).
        if (
            plan_optimization
            and mpc_reserve is not None
            and (not feasible or unserved_wh > 1.0)
        ):
            decision.blackout_risk = BlackoutRisk.CRITICAL
            decision.blackout_risk_score = max(decision.blackout_risk_score, 0.9)
            if decision.explanation is not None:
                decision.explanation.risk.label = BlackoutRisk.CRITICAL
                decision.explanation.risk.score = decision.blackout_risk_score
        if plan_optimization:
            decision.summary = Msg(
                key=decision.summary.key,
                params={
                    **decision.summary.params,
                    "has_mpc": "yes",
                    "horizon": self._engine_cfg.mpc_horizon_hours,
                    "reserve": int(mpc_reserve) if mpc_reserve is not None else "",
                    "survivable": (
                        "yes"
                        if mpc_reserve is not None and feasible and unserved_wh <= 1.0
                        else "no"
                    ),
                    "kwh": f"{unserved_wh/1000:.1f}",
                },
            )
            if decision.explanation is not None and pin is not None:
                decision.explanation.reserve.mpc_soc = (
                    decision.reserve.target_soc
                    if decision.reserve.source.value == "mpc"
                    else pin
                )
        decision.ts = utcnow()
        return decision

    def _solve(
        self,
        telemetry: Telemetry,
        forecast: ForecastBundle | None,
        *,
        smoothed_load_w: float | None = None,
        rule: RuleEngine | None = None,
    ) -> tuple[float | None, float, bool]:
        """Return (reserve_soc_pct, expected_unserved_wh, feasible).

        Grid is assumed ABSENT across the horizon. We maximise served load
        (minimise unserved) and minimise curtailment using a battery dispatch LP.
        The reserve % surfaced is the peak forward energy the battery must hold
        to bridge upcoming deficits.
        """
        if not forecast or not forecast.load:
            return None, 0.0, False

        cap_wh = self._battery.capacity_kwh * 1000.0
        floor_wh = cap_wh * self._battery.min_soc_floor / 100.0
        eff = self._battery.round_trip_efficiency
        dt = 1.0  # forecast is hourly
        max_power_w = self._effective_max_charge_a() * self._battery.nominal_voltage
        max_charge_w = max_discharge_w = max_power_w

        w_r = self._weights[OptimizationPriority.resilience]
        w_s = self._weights[OptimizationPriority.savings]
        w_ss = self._weights[OptimizationPriority.self_sufficiency]
        smooth = smoothed_load_w
        if smooth is None and telemetry.load_power is not None:
            smooth = float(telemetry.load_power)
        prev = rule.last_effective_critical_w if rule is not None else None
        leff, _ = effective_critical_w(
            critical_load_w=self._reserve.critical_load_w,
            smoothed_load_w=(
                smooth if self._reserve.adaptive_load_enabled else None
            ),
            adaptive_enabled=self._reserve.adaptive_load_enabled,
            adaptive_cap_w=self._reserve.adaptive_load_cap_w,
            resilience_weight=w_r,
            savings_weight=w_s,
            self_sufficiency_weight=w_ss,
            prev_effective_w=prev,
        )

        # Align hourly solar to load timeline over the horizon.
        horizon = min(self._engine_cfg.mpc_horizon_hours, len(forecast.load))
        solar_by_ts = {
            p.ts.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0): p.pv_power_w
            for p in forecast.solar
        }
        now = utcnow().replace(minute=0, second=0, microsecond=0)
        pv = []
        load = []
        for i in range(horizon):
            ts = now + timedelta(hours=i)
            pv.append(max(0.0, solar_by_ts.get(ts, 0.0)))
            load.append(max(leff, self._load_at_ts(forecast, ts)))

        if telemetry.battery_soc is None:
            return None, 0.0, False
        soc0 = telemetry.battery_soc
        e0 = cap_wh * soc0 / 100.0

        prob = pulp.LpProblem("mpc_dispatch", pulp.LpMinimize)
        N = horizon
        ch = [pulp.LpVariable(f"ch_{t}", 0, max_charge_w) for t in range(N)]
        dch = [pulp.LpVariable(f"dch_{t}", 0, max_discharge_w) for t in range(N)]
        uns = [pulp.LpVariable(f"uns_{t}", 0) for t in range(N)]
        cur = [pulp.LpVariable(f"cur_{t}", 0) for t in range(N)]
        e = [pulp.LpVariable(f"e_{t}", floor_wh, cap_wh) for t in range(N + 1)]

        prob += e[0] == e0
        for t in range(N):
            pv_to_load = pulp.LpVariable(f"pv2l_{t}", 0)
            # PV split: to load, to battery (ch), or curtailed.
            prob += pv_to_load + ch[t] + cur[t] == pv[t]
            prob += pv_to_load <= load[t]
            # Load served by PV + discharge + unserved.
            prob += pv_to_load + dch[t] + uns[t] == load[t]
            # Battery energy balance (Wh over dt hours).
            prob += e[t + 1] == e[t] + (ch[t] * eff - dch[t]) * dt

        # Objective: resilience (unserved) >> self-sufficiency (curtailment).
        w_resilience, w_curtail = mpc_weights(self._weights)
        prob += w_resilience * pulp.lpSum(uns) + w_curtail * pulp.lpSum(cur)

        try:
            prob.solve(pulp.PULP_CBC_CMD(msg=False))
        except Exception as ex:  # noqa: BLE001
            log.warning("MPC solve error: %s", ex)
            return None, 0.0, False

        status = pulp.LpStatus[prob.status]
        unserved_wh = sum(max(0.0, v.value() or 0.0) for v in uns)
        feasible = status == "Optimal"

        # Reserve = peak forward cumulative deficit (Wh) -> % on top of floor.
        peak_def = self._peak_forward_deficit(pv, load, eff)
        peak_def *= buffer_scale(w_r)
        peak_def *= savings_buffer_relief(w_s)
        reserve_pct = min(
            self._battery.max_soc_ceiling,
            self._battery.min_soc_floor + 100.0 * peak_def / cap_wh,
        )
        return round(reserve_pct, 1), unserved_wh, feasible

    @staticmethod
    def _load_at_ts(forecast: ForecastBundle, ts) -> float:
        """Load at hour ts via timestamp match / nearest (±1h), else last point."""
        key = ts.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
        if not forecast.load:
            return 400.0
        for p in forecast.load:
            pkey = p.ts.astimezone(timezone.utc).replace(
                minute=0, second=0, microsecond=0
            )
            if pkey == key:
                return p.load_power_w
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
        return forecast.load[-1].load_power_w

    @staticmethod
    def _load_at(forecast: ForecastBundle, i: int) -> float:
        if i < len(forecast.load):
            return forecast.load[i].load_power_w
        return forecast.load[-1].load_power_w if forecast.load else 400.0

    @staticmethod
    def _peak_forward_deficit(pv: list[float], load: list[float], eff: float) -> float:
        cum = 0.0
        peak = 0.0
        for p, l in zip(pv, load):
            cum += max(0.0, l - p)
            cum -= max(0.0, p - l) * eff
            cum = max(0.0, cum)
            peak = max(peak, cum)
        return peak
