"""Grid charge ramp: cap-chain factors + per-cycle smoothing."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ..config import BatteryConfig, GridChargeConfig, GridChargeFactor
from ..models import (
    BlackoutRisk,
    ForecastBundle,
    GridChargePlan,
    GridStats,
    ReserveTarget,
    Telemetry,
    utcnow,
)


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


@dataclass(frozen=True)
class FactorResult:
    ceiling_a: float
    note: str


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _max_amps(ctx: RampContext) -> float:
    return ctx.battery.max_grid_charge_a


def _resolve_site_tz(tz_name: str) -> timezone | ZoneInfo:
    if not tz_name or tz_name == "auto":
        return timezone.utc
    try:
        return ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError):
        return timezone.utc


def _remaining_solar_wh(ctx: RampContext, now: datetime) -> float:
    if not ctx.forecast or not ctx.forecast.solar:
        return 0.0
    site_tz = _resolve_site_tz(ctx.site_timezone)
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
        f"SOC {soc:.0f}% vs target {ctx.target_soc:.0f}% (urgency {urgency:.0%})",
    )


def _eval_remaining_solar_today(ctx: RampContext) -> FactorResult:
    max_a = _max_amps(ctx)
    soc = ctx.telemetry.battery_soc if ctx.telemetry.battery_soc is not None else 0.0
    if soc >= ctx.target_soc:
        return FactorResult(max_a, "SOC at/above target — no trim")

    needed_wh = (ctx.target_soc - soc) * ctx.battery.usable_wh_per_soc
    remaining_wh = _remaining_solar_wh(ctx, utcnow())
    if remaining_wh <= 0:
        return FactorResult(max_a, "no remaining solar forecast")

    cover = remaining_wh / max(needed_wh, 1.0)
    if cover >= 1.2:
        scale = _clamp(needed_wh / remaining_wh, 0.05, 1.0)
        ceiling = max_a * scale
        return FactorResult(
            ceiling,
            f"remaining solar {remaining_wh/1000:.1f} kWh covers need ({cover:.0%})",
        )
    return FactorResult(max_a, f"remaining solar {remaining_wh/1000:.1f} kWh insufficient")


def _eval_next_solar_power(ctx: RampContext) -> FactorResult:
    max_a = _max_amps(ctx)
    if not ctx.forecast or not ctx.forecast.solar:
        return FactorResult(max_a, "no solar forecast")

    now = utcnow().replace(minute=0, second=0, microsecond=0)
    horizon = ctx.grid_charge.next_solar_horizon_hours
    end = now + timedelta(hours=horizon)
    peak_w = 0.0
    for p in ctx.forecast.solar:
        pts = p.ts.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
        if now <= pts <= end:
            peak_w = max(peak_w, p.pv_power_w)

    if peak_w <= 0:
        return FactorResult(max_a, f"no solar in next {horizon}h")

    max_charge_w = max_a * ctx.battery.nominal_voltage
    if peak_w >= max_charge_w * 0.5:
        scale = _clamp(1.0 - (peak_w / max(max_charge_w, 1.0)), 0.1, 1.0)
        ceiling = max_a * scale
        return FactorResult(
            ceiling,
            f"peak {peak_w/1000:.1f} kW solar in next {horizon}h",
        )
    return FactorResult(max_a, f"modest solar ({peak_w/1000:.1f} kW) in next {horizon}h")


def _eval_load_power(ctx: RampContext) -> FactorResult:
    max_a = _max_amps(ctx)
    load = ctx.telemetry.load_power
    pv = ctx.telemetry.pv_power
    if load is None or pv is None:
        return FactorResult(max_a, "load/PV unknown")

    deficit_w = load - pv
    if deficit_w <= 0:
        ceiling = max_a * 0.25
        return FactorResult(ceiling, f"surplus PV ({-deficit_w:.0f} W net)")

    max_charge_w = max_a * ctx.battery.nominal_voltage
    ratio = _clamp(deficit_w / max(max_charge_w, 1.0), 0.0, 1.0)
    ceiling = max_a * max(0.3, ratio)
    return FactorResult(ceiling, f"net import need {deficit_w:.0f} W")


def _eval_battery_power(ctx: RampContext) -> FactorResult:
    max_a = _max_amps(ctx)
    bp = ctx.telemetry.battery_power
    if bp is None:
        return FactorResult(max_a, "battery power unknown")

    if bp <= 0:
        return FactorResult(max_a, "not charging from PV")

    charge_a = bp / max(ctx.battery.nominal_voltage, 1.0)
    ceiling = max(0.0, max_a - charge_a)
    return FactorResult(
        ceiling,
        f"already charging {charge_a:.0f} A from PV ({bp:.0f} W)",
    )


def _eval_grid_window(ctx: RampContext) -> FactorResult:
    max_a = _max_amps(ctx)
    if ctx.grid_stats is None:
        return FactorResult(max_a, "grid stats unknown")

    window = ctx.grid_stats.avg_window_minutes
    if window <= 0:
        return FactorResult(max_a, "no historical grid windows")

    if window <= 20:
        return FactorResult(max_a, f"short grid window ({window:.0f} min avg)")

    if window >= 180:
        ceiling = max_a * 0.4
        return FactorResult(ceiling, f"long grid window ({window:.0f} min avg)")

    # 20–180 min: linear scale from max to 40% of max
    t = (window - 20) / 160.0
    scale = 1.0 - t * 0.6
    ceiling = max_a * scale
    return FactorResult(ceiling, f"grid window {window:.0f} min avg")


def _eval_blackout_risk(ctx: RampContext) -> FactorResult:
    max_a = _max_amps(ctx)
    score = _clamp(ctx.blackout_risk_score, 0.0, 1.0)
    scale = 0.4 + 0.6 * score
    ceiling = max_a * scale
    return FactorResult(
        ceiling,
        f"risk {ctx.blackout_risk.value} (score {score:.0%})",
    )


def _eval_solar_bridge(ctx: RampContext) -> FactorResult:
    max_a = _max_amps(ctx)
    soc = ctx.telemetry.battery_soc if ctx.telemetry.battery_soc is not None else 0.0
    bridge = ctx.reserve.solar_bridge_soc
    if soc >= bridge:
        return FactorResult(max_a, "at/above bridge — no trim")
    gap = max(0.0, bridge - soc)
    span = max(bridge - ctx.battery.min_soc_floor, 1.0)
    urgency = _clamp(gap / span, 0.0, 1.0)
    ceiling = max_a * max(0.25, urgency)
    return FactorResult(
        ceiling,
        f"bridge gap {gap:.0f}% (bridge target {bridge:.0f}%)",
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
            rationale="Grid absent; disable grid charge.",
        )

    soc = ctx.telemetry.battery_soc if ctx.telemetry.battery_soc is not None else 0.0
    if soc >= ctx.target_soc:
        return GridChargePlan(
            enabled=False,
            target_amps=0.0,
            max_amps=max_a,
            rationale=(
                f"Reserve target {ctx.target_soc:.0f}% met "
                f"(SOC {soc:.0f}%); stop grid charge."
            ),
        )

    target = max_a
    notes: list[str] = []
    for factor in cfg.factor_order:
        evaluator = _EVALUATORS.get(factor)
        if evaluator is None:
            continue
        result = evaluator(ctx)
        ceiling = _clamp(result.ceiling_a, 0.0, max_a)
        target = min(target, ceiling)
        notes.append(f"{factor.value}: {result.note} -> {ceiling:.0f} A")

    if target < cfg.off_threshold_a:
        return GridChargePlan(
            enabled=False,
            target_amps=0.0,
            max_amps=max_a,
            rationale="Cap chain: " + "; ".join(notes) + "; below off threshold.",
        )

    if target > 0 and target < cfg.min_grid_charge_a:
        target = cfg.min_grid_charge_a

    if ctx.last_amps is not None:
        delta = target - ctx.last_amps
        delta = _clamp(delta, -cfg.ramp_step_a, cfg.ramp_step_a)
        target = _clamp(ctx.last_amps + delta, 0.0, max_a)

    rationale = "Cap chain: " + "; ".join(notes) if notes else "Cap chain: no factors applied."
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
    rationale: str,
) -> GridChargePlan:
    return GridChargePlan(
        enabled=enabled,
        target_amps=target_amps,
        max_amps=max_amps,
        rationale=rationale,
    )
