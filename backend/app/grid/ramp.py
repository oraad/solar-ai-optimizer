"""Grid charge ramp: cap-chain factors + per-cycle smoothing."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from ..config import BatteryConfig, GridChargeConfig, GridChargeFactor
from ..engine.priorities import FACTOR_BLEND, RANK_WEIGHTS, blend_ceiling, resolve_weights
from ..i18n import msg
from ..models import (
    BlackoutRisk,
    ForecastBundle,
    GridChargePlan,
    GridStats,
    Msg,
    ReserveTarget,
    Telemetry,
    utcnow,
)
from ..tz import resolve_site_tz


@dataclass(frozen=True)
class RampContext:
    telemetry: Telemetry
    forecast: ForecastBundle | None
    grid_stats: GridStats | None
    reserve: ReserveTarget
    target_soc: float
    blackout_risk: BlackoutRisk
    blackout_risk_score: float
    battery: BatteryConfig
    grid_charge: GridChargeConfig
    last_amps: float | None = None
    site_timezone: str = "auto"
    site_timezone_resolved: str | None = None
    priority_weights: dict[str, float] | None = None


@dataclass(frozen=True)
class FactorResult:
    ceiling_a: float
    note: Msg


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _max_amps(ctx: RampContext) -> float:
    return ctx.grid_charge.max_grid_charge_a


def _remaining_solar_wh(ctx: RampContext, now: datetime) -> float:
    if not ctx.forecast or not ctx.forecast.solar:
        return 0.0
    site_tz = resolve_site_tz(
        ctx.site_timezone,
        auto_hint=ctx.site_timezone_resolved,
    )
    local = now.astimezone(site_tz)
    end_of_day = local.replace(hour=23, minute=59, second=59, microsecond=999999)
    total = 0.0
    for p in ctx.forecast.solar:
        pts = p.ts.astimezone(site_tz)
        if pts >= local and pts <= end_of_day:
            total += p.pv_energy_wh if p.pv_energy_wh > 0 else p.pv_power_w
    return total


def _eval_soc_gap(ctx: RampContext) -> FactorResult:
    max_a = _max_amps(ctx)
    soc = ctx.telemetry.battery_soc if ctx.telemetry.battery_soc is not None else 0.0
    span = max(ctx.target_soc - ctx.battery.min_soc_floor, 1.0)
    deficit = max(0.0, ctx.target_soc - soc)
    urgency = _clamp(deficit / span, 0.0, 1.0)
    ceiling = max_a * urgency
    return FactorResult(
        ceiling,
        msg(
            "engine.ramp.soc_gap",
            soc=int(round(soc)),
            target=int(round(ctx.target_soc)),
            urgency=int(round(urgency * 100)),
        ),
    )


def _eval_remaining_solar_today(ctx: RampContext) -> FactorResult:
    max_a = _max_amps(ctx)
    soc = ctx.telemetry.battery_soc if ctx.telemetry.battery_soc is not None else 0.0
    if soc >= ctx.target_soc:
        return FactorResult(max_a, msg("engine.ramp.remaining_solar.at_target"))

    needed_wh = (ctx.target_soc - soc) * ctx.battery.usable_wh_per_soc
    remaining_wh = _remaining_solar_wh(ctx, utcnow())
    if remaining_wh <= 0:
        return FactorResult(max_a, msg("engine.ramp.remaining_solar.no_forecast"))

    cover = remaining_wh / max(needed_wh, 1.0)
    if cover >= 1.2:
        scale = _clamp(needed_wh / remaining_wh, 0.05, 1.0)
        ceiling = max_a * scale
        return FactorResult(
            ceiling,
            msg(
                "engine.ramp.remaining_solar.covers",
                kwh=f"{remaining_wh/1000:.1f}",
                cover=int(round(cover * 100)),
            ),
        )
    return FactorResult(
        max_a,
        msg("engine.ramp.remaining_solar.insufficient", kwh=f"{remaining_wh/1000:.1f}"),
    )


def _eval_next_solar_power(ctx: RampContext) -> FactorResult:
    max_a = _max_amps(ctx)
    if not ctx.forecast or not ctx.forecast.solar:
        return FactorResult(max_a, msg("engine.ramp.next_solar.no_forecast"))

    now = utcnow().replace(minute=0, second=0, microsecond=0)
    horizon = ctx.grid_charge.next_solar_horizon_hours
    end = now + timedelta(hours=horizon)
    peak_w = 0.0
    for p in ctx.forecast.solar:
        pts = p.ts.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
        if now <= pts <= end:
            peak_w = max(peak_w, p.pv_power_w)

    if peak_w <= 0:
        return FactorResult(max_a, msg("engine.ramp.next_solar.none", horizon=horizon))

    max_charge_w = max_a * ctx.battery.nominal_voltage
    if peak_w >= max_charge_w * 0.5:
        scale = _clamp(1.0 - (peak_w / max(max_charge_w, 1.0)), 0.1, 1.0)
        ceiling = max_a * scale
        return FactorResult(
            ceiling,
            msg(
                "engine.ramp.next_solar.peak",
                kw=f"{peak_w/1000:.1f}",
                horizon=horizon,
            ),
        )
    return FactorResult(
        max_a,
        msg("engine.ramp.next_solar.modest", kw=f"{peak_w/1000:.1f}", horizon=horizon),
    )


def _eval_load_power(ctx: RampContext) -> FactorResult:
    max_a = _max_amps(ctx)
    load = ctx.telemetry.load_power
    pv = ctx.telemetry.pv_power
    if load is None or pv is None:
        return FactorResult(max_a, msg("engine.ramp.load.unknown"))

    deficit_w = load - pv
    if deficit_w <= 0:
        ceiling = max_a * 0.25
        return FactorResult(ceiling, msg("engine.ramp.load.surplus", watts=int(-deficit_w)))

    max_charge_w = max_a * ctx.battery.nominal_voltage
    ratio = _clamp(deficit_w / max(max_charge_w, 1.0), 0.0, 1.0)
    ceiling = max_a * max(0.3, ratio)
    return FactorResult(ceiling, msg("engine.ramp.load.import_need", watts=int(deficit_w)))


def _eval_battery_power(ctx: RampContext) -> FactorResult:
    max_a = _max_amps(ctx)
    bp = ctx.telemetry.battery_power
    if bp is None:
        return FactorResult(max_a, msg("engine.ramp.battery.unknown"))

    if bp <= 0:
        return FactorResult(max_a, msg("engine.ramp.battery.not_charging"))

    charge_a = bp / max(ctx.battery.nominal_voltage, 1.0)
    ceiling = max(0.0, max_a - charge_a)
    return FactorResult(
        ceiling,
        msg(
            "engine.ramp.battery.charging",
            amps=int(round(charge_a)),
            watts=int(bp),
        ),
    )


def _eval_grid_window(ctx: RampContext) -> FactorResult:
    max_a = _max_amps(ctx)
    if ctx.grid_stats is None:
        return FactorResult(max_a, msg("engine.ramp.grid_window.unknown"))

    window = ctx.grid_stats.avg_window_minutes
    if window <= 0:
        return FactorResult(max_a, msg("engine.ramp.grid_window.none"))

    if window <= 20:
        return FactorResult(max_a, msg("engine.ramp.grid_window.short", minutes=int(window)))

    if window >= 180:
        ceiling = max_a * 0.4
        return FactorResult(ceiling, msg("engine.ramp.grid_window.long", minutes=int(window)))

    # 20–180 min: linear scale from max to 40% of max
    t = (window - 20) / 160.0
    scale = 1.0 - t * 0.6
    ceiling = max_a * scale
    return FactorResult(ceiling, msg("engine.ramp.grid_window.mid", minutes=int(window)))


def _eval_blackout_risk(ctx: RampContext) -> FactorResult:
    max_a = _max_amps(ctx)
    score = _clamp(ctx.blackout_risk_score, 0.0, 1.0)
    scale = 0.4 + 0.6 * score
    ceiling = max_a * scale
    return FactorResult(
        ceiling,
        msg(
            "engine.ramp.blackout_risk",
            risk=ctx.blackout_risk.value,
            score=int(round(score * 100)),
        ),
    )


def _eval_solar_bridge(ctx: RampContext) -> FactorResult:
    max_a = _max_amps(ctx)
    soc = ctx.telemetry.battery_soc if ctx.telemetry.battery_soc is not None else 0.0
    bridge = ctx.reserve.solar_bridge_soc
    if soc >= bridge:
        return FactorResult(max_a, msg("engine.ramp.solar_bridge.at_target"))
    gap = max(0.0, bridge - soc)
    span = max(bridge - ctx.battery.min_soc_floor, 1.0)
    urgency = _clamp(gap / span, 0.0, 1.0)
    ceiling = max_a * max(0.25, urgency)
    return FactorResult(
        ceiling,
        msg(
            "engine.ramp.solar_bridge.gap",
            gap=int(round(gap)),
            bridge=int(round(bridge)),
        ),
    )


_EVALUATORS = {
    GridChargeFactor.soc_gap: _eval_soc_gap,
    GridChargeFactor.remaining_solar_today: _eval_remaining_solar_today,
    GridChargeFactor.next_solar_power: _eval_next_solar_power,
    GridChargeFactor.load_power: _eval_load_power,
    GridChargeFactor.battery_power: _eval_battery_power,
    GridChargeFactor.grid_window: _eval_grid_window,
    GridChargeFactor.blackout_risk: _eval_blackout_risk,
    GridChargeFactor.solar_bridge: _eval_solar_bridge,
}


def compute_ramp_plan(ctx: RampContext) -> GridChargePlan:
    """Cap-chain factor pipeline with optional per-cycle ramp smoothing."""
    max_a = _max_amps(ctx)
    cfg = ctx.grid_charge

    if not ctx.telemetry.grid_present:
        return GridChargePlan(
            enabled=False,
            target_amps=0.0,
            max_amps=max_a,
            rationale=msg("engine.grid.absent"),
        )

    soc = ctx.telemetry.battery_soc if ctx.telemetry.battery_soc is not None else 0.0
    if soc >= ctx.target_soc:
        return GridChargePlan(
            enabled=False,
            target_amps=0.0,
            max_amps=max_a,
            rationale=msg(
                "engine.grid.reserve_met",
                target=round(ctx.target_soc, 0),
                soc=round(soc, 0),
            ),
        )

    target = max_a
    note_entries: list[dict[str, object]] = []
    weights = ctx.priority_weights or {
        k.value: v for k, v in resolve_weights().items()
    }
    for factor in cfg.factor_order:
        evaluator = _EVALUATORS.get(factor)
        if evaluator is None:
            continue
        result = evaluator(ctx)
        ceiling = _clamp(result.ceiling_a, 0.0, max_a)
        bucket = FACTOR_BLEND.get(factor.value)
        if bucket is not None:
            priority, mode = bucket
            weight = weights.get(priority.value, RANK_WEIGHTS[-1])
            ceiling = _clamp(
                blend_ceiling(ceiling, max_a, weight, mode, priority), 0.0, max_a
            )
        target = min(target, ceiling)
        note_entries.append(
            {
                "factor": factor.value,
                "k": result.note.key,
                "p": result.note.params,
                "ceiling": int(round(ceiling)),
            }
        )

    notes_json = json.dumps(note_entries, ensure_ascii=False, separators=(",", ":"))
    if target < cfg.off_threshold_a:
        return GridChargePlan(
            enabled=False,
            target_amps=0.0,
            max_amps=max_a,
            rationale=msg(
                "engine.grid.cap_chain_below_threshold",
                note_entries=notes_json,
            ),
        )

    if target > 0 and target < cfg.min_grid_charge_a:
        target = cfg.min_grid_charge_a

    if ctx.last_amps is not None:
        delta = target - ctx.last_amps
        delta = _clamp(delta, -cfg.ramp_step_a, cfg.ramp_step_a)
        target = _clamp(ctx.last_amps + delta, 0.0, max_a)

    rationale = (
        msg("engine.grid.cap_chain", note_entries=notes_json)
        if note_entries
        else msg("engine.grid.cap_chain_no_factors")
    )
    return GridChargePlan(
        enabled=True,
        target_amps=round(target, 1),
        max_amps=max_a,
        rationale=rationale,
    )


def legacy_plan(
    *,
    enabled: bool,
    target_amps: float,
    max_amps: float,
    rationale: Msg,
) -> GridChargePlan:
    return GridChargePlan(
        enabled=enabled,
        target_amps=target_amps,
        max_amps=max_amps,
        rationale=rationale,
    )
