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
from datetime import timedelta, timezone

# Hard dependency for this optional engine. ImportError -> fallback to rules.
import pulp  # noqa: F401

from ..config import BatteryConfig, EngineConfig, LoadSheddingConfig, ReserveConfig
from ..grid.reactive import ReactiveGrid
from ..models import (
    BlackoutRisk,
    Decision,
    ForecastBundle,
    GridStats,
    Override,
    Telemetry,
    utcnow,
)
from .rules import RuleEngine

log = logging.getLogger("engine.mpc")


class MPCEngine:
    def __init__(
        self,
        battery: BatteryConfig,
        reserve: ReserveConfig,
        engine_cfg: EngineConfig,
        shedding: LoadSheddingConfig | None = None,
        total_kwp: float = 1.0,
    ) -> None:
        self._battery = battery
        self._reserve = reserve
        self._engine_cfg = engine_cfg
        self._shedding = shedding or LoadSheddingConfig()
        self._total_kwp = total_kwp
        self._rule: RuleEngine | None = None

    def _rule_engine(self, reactive: ReactiveGrid) -> RuleEngine:
        if self._rule is None:
            self._rule = RuleEngine(
                self._battery,
                self._reserve,
                self._engine_cfg,
                reactive,
                self._shedding,
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
    ) -> Decision:
        # Build the action set with the rule engine, but pin the reserve target
        # to the MPC-optimised value (unless the operator pinned their own).
        rule = self._rule_engine(reactive)

        mpc_reserve, unserved_wh, feasible = self._solve(telemetry, forecast)

        eff_override = Override(**(override.model_dump() if override else {}))
        if eff_override.reserve_soc is None and mpc_reserve is not None:
            eff_override.reserve_soc = mpc_reserve

        decision = rule.decide(
            telemetry,
            forecast,
            grid_stats,
            eff_override,
            shadow_mode,
            telemetry_stale=telemetry_stale,
        )

        # Enrich risk + summary with MPC survivability result.
        if not feasible or unserved_wh > 1.0:
            decision.blackout_risk = BlackoutRisk.CRITICAL
            decision.blackout_risk_score = max(decision.blackout_risk_score, 0.9)
        note = (
            f"MPC[{self._engine_cfg.mpc_horizon_hours}h]: "
            f"reserve={mpc_reserve:.0f}% " if mpc_reserve is not None else "MPC: "
        )
        note += (
            "survivable (grid-absent)."
            if feasible and unserved_wh <= 1.0
            else f"NOT survivable grid-absent: ~{unserved_wh/1000:.1f} kWh unserved."
        )
        decision.summary = f"{note} {decision.summary}"
        decision.ts = utcnow()
        return decision

    def _solve(
        self, telemetry: Telemetry, forecast: ForecastBundle | None
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
        max_charge_w = self._battery.max_charge_a * self._battery.nominal_voltage
        max_discharge_w = max_charge_w  # symmetric assumption

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
            load.append(max(0.0, self._load_at(forecast, i)))

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
        w_resilience = 1000.0
        w_curtail = 1.0
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
        reserve_pct = min(
            self._battery.max_soc_ceiling,
            self._battery.min_soc_floor + 100.0 * peak_def / cap_wh,
        )
        return round(reserve_pct, 1), unserved_wh, feasible

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
