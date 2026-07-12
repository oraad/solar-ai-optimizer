"""Optimization priority rank → engine weight multipliers."""

from __future__ import annotations

from enum import Enum

from ..config import OptimizationPriority
from ..i18n import get_locale, t

RANK_WEIGHTS = (1.0, 0.4, 0.15)

DEFAULT_PRIORITY_ORDER = [
    OptimizationPriority.resilience,
    OptimizationPriority.savings,
    OptimizationPriority.self_sufficiency,
]

DEFAULT_PRIORITY_WEIGHTS: dict[OptimizationPriority, float] = {
    OptimizationPriority.resilience: RANK_WEIGHTS[0],
    OptimizationPriority.savings: RANK_WEIGHTS[1],
    OptimizationPriority.self_sufficiency: RANK_WEIGHTS[2],
}


def priority_scale(weight: float, priority: OptimizationPriority) -> float:
    """1.0 at default rank; >1 when promoted, <1 when demoted."""
    base = DEFAULT_PRIORITY_WEIGHTS[priority]
    if base <= 0:
        return 1.0
    return weight / base


class BlendMode(str, Enum):
    TRIM = "trim"
    URGENCY = "urgency"
    SAVINGS = "savings"


FACTOR_BLEND: dict[str, tuple[OptimizationPriority, BlendMode]] = {
    "soc_gap": (OptimizationPriority.resilience, BlendMode.URGENCY),
    "blackout_risk": (OptimizationPriority.resilience, BlendMode.URGENCY),
    "solar_bridge": (OptimizationPriority.resilience, BlendMode.URGENCY),
    "grid_window": (OptimizationPriority.savings, BlendMode.SAVINGS),
    "remaining_solar_today": (OptimizationPriority.self_sufficiency, BlendMode.TRIM),
    "next_solar_power": (OptimizationPriority.self_sufficiency, BlendMode.TRIM),
    "load_power": (OptimizationPriority.self_sufficiency, BlendMode.TRIM),
    "battery_power": (OptimizationPriority.self_sufficiency, BlendMode.TRIM),
}


def resolve_weights(
    order: list[OptimizationPriority] | None = None,
) -> dict[OptimizationPriority, float]:
    """Map each priority to a rank weight (1st=1.0, 2nd=0.4, 3rd=0.15)."""
    seq = order or DEFAULT_PRIORITY_ORDER
    weights = dict.fromkeys(OptimizationPriority, RANK_WEIGHTS[-1])
    for rank, priority in enumerate(seq[: len(RANK_WEIGHTS)]):
        weights[priority] = RANK_WEIGHTS[rank]
    return weights


def buffer_scale(resilience_weight: float) -> float:
    """Scale solar-bridge buffer %; 1.0 at default resilience rank."""
    lo, hi = 0.15, 1.0
    scale_lo = 0.90
    t = (resilience_weight - lo) / (hi - lo)
    return max(scale_lo, min(1.0, scale_lo + t * (1.0 - scale_lo)))


def savings_buffer_relief(savings_weight: float) -> float:
    """Leaner bridge buffers when savings ranks high; 1.0 at default savings rank."""
    pivot = RANK_WEIGHTS[1]
    relief_floor = 0.92
    if savings_weight <= pivot:
        return 1.0
    t = (savings_weight - pivot) / (1.0 - pivot)
    return max(relief_floor, 1.0 - t * (1.0 - relief_floor))


def adaptive_load_scale(
    resilience_weight: float,
    savings_weight: float,
    self_sufficiency_weight: float,
) -> float:
    """How much of smoothed load above critical to trust (0..1).

    Resilience 1st → 1.0; resilience last → 0.35. Savings 1st leans ~0.85;
    self-sufficiency 1st leans ~0.90. Default rank order → 1.0.
    Final result is always clamped to [0.35, 1.0].
    """
    lo, hi = RANK_WEIGHTS[-1], RANK_WEIGHTS[0]
    t = (resilience_weight - lo) / (hi - lo)
    a = max(0.35, min(1.0, 0.35 + t * (1.0 - 0.35)))
    if savings_weight >= RANK_WEIGHTS[0] - 1e-9:
        a *= 0.85
    if self_sufficiency_weight >= RANK_WEIGHTS[0] - 1e-9:
        a *= 0.90
    return max(0.35, min(1.0, a))


def autonomy_hours_scale(resilience_weight: float) -> float:
    """Scale min_autonomy_hours; 1.0 at default resilience rank, 0.85 when last."""
    lo, hi = RANK_WEIGHTS[-1], RANK_WEIGHTS[0]
    t = (resilience_weight - lo) / (hi - lo)
    return max(0.85, min(1.0, 0.85 + t * (1.0 - 0.85)))


def effective_critical_w(
    *,
    critical_load_w: float,
    smoothed_load_w: float | None,
    adaptive_enabled: bool,
    adaptive_cap_w: float | None,
    resilience_weight: float,
    savings_weight: float,
    self_sufficiency_weight: float,
    prev_effective_w: float | None = None,
    hysteresis_down_frac: float = 0.10,
) -> tuple[float, float]:
    """Return (L_eff_used, blend_a).

    L_eff = critical + a * max(0, smooth - critical), capped, with downward hysteresis.
    Cap is enforced after hysteresis so it remains a hard ceiling.
    """
    crit = max(0.0, critical_load_w)
    if not adaptive_enabled or smoothed_load_w is None:
        return crit, 0.0
    a = adaptive_load_scale(
        resilience_weight, savings_weight, self_sufficiency_weight
    )
    smooth = max(0.0, smoothed_load_w)
    raw = crit + a * max(0.0, smooth - crit)
    cap = adaptive_cap_w if adaptive_cap_w is not None else 3.0 * max(crit, 1.0)
    hard_cap = max(crit, cap)
    raw = min(raw, hard_cap)
    if prev_effective_w is not None and prev_effective_w > raw:
        # Move down slowly: at most hysteresis_down_frac of previous per cycle.
        floor = prev_effective_w * (1.0 - hysteresis_down_frac)
        used = max(raw, floor)
    else:
        used = raw
    return min(used, hard_cap), a


def mean_load_power_w(
    samples: list[float | None],
    *,
    min_samples: int = 3,
    fallback: float | None = None,
) -> float | None:
    """Mean of non-null load samples; None if fewer than min_samples and no fallback."""
    vals = [float(v) for v in samples if v is not None]
    if len(vals) >= min_samples:
        return sum(vals) / len(vals)
    return fallback


def discharge_power_w(battery_power: float | None) -> float | None:
    """Discharge watts from battery_power (+charge / -discharge); None if unknown."""
    if battery_power is None:
        return None
    return max(0.0, -float(battery_power))


def smoothed_adaptive_load_w(
    rows: list,
    telemetry,
    *,
    min_samples: int = 3,
) -> tuple[float | None, float | None]:
    """Return (L_smooth, L_discharge) for adaptive reserve.

    L_load = mean(load_power) when enough samples, else thin-history latest load.
    L_dis = mean(max(0, -battery_power)) when enough samples, else latest discharge.
    L_smooth = max(L_load, L_dis) when either is set (no additive double-count).
    """
    load_samples = [getattr(r, "load_power", None) for r in rows]
    dis_samples = [discharge_power_w(getattr(r, "battery_power", None)) for r in rows]

    latest_load = (
        float(telemetry.load_power) if getattr(telemetry, "load_power", None) is not None else None
    )
    latest_dis = discharge_power_w(getattr(telemetry, "battery_power", None))

    l_load = mean_load_power_w(
        load_samples, min_samples=min_samples, fallback=latest_load
    )
    l_dis = mean_load_power_w(
        dis_samples, min_samples=min_samples, fallback=latest_dis
    )

    if l_load is None and l_dis is None:
        return None, None
    if l_load is None:
        return l_dis, l_dis
    if l_dis is None:
        return l_load, None
    return max(l_load, l_dis), l_dis


def grid_present_risk_multiplier(
    resilience_weight: float,
    savings_weight: float,
    *,
    present_elapsed_minutes: float | None = None,
    remaining_window_minutes: float | None = None,
) -> float:
    """Grid-present risk discount; fades toward 1.0 as opportunity is exhausted.

    Base ~0.5 at default ranks. When elapsed/remaining are known, fade from base
    toward 1.0 as elapsed/(elapsed+remaining) → 1 (near end of trusted window).
    """
    pivot_r, pivot_s = RANK_WEIGHTS[0], RANK_WEIGHTS[1]
    mult = 0.5
    mult += 0.15 * (pivot_r - resilience_weight) / (pivot_r - RANK_WEIGHTS[-1])
    mult -= 0.10 * (savings_weight - pivot_s) / (1.0 - pivot_s)
    mult = max(0.35, min(0.65, mult))
    if present_elapsed_minutes is None or remaining_window_minutes is None:
        return mult
    elapsed = max(0.0, float(present_elapsed_minutes))
    remain = max(0.0, float(remaining_window_minutes))
    trusted = elapsed + remain
    if trusted <= 1e-9:
        return 1.0
    t = min(1.0, max(0.0, elapsed / trusted))
    return mult + (1.0 - mult) * t


def mpc_weights(
    weights: dict[OptimizationPriority, float],
) -> tuple[float, float]:
    """Return (w_resilience, w_curtail) for the MPC objective."""
    w_res = 1000.0 * max(weights[OptimizationPriority.resilience], RANK_WEIGHTS[-1])
    w_cur = max(
        0.15,
        weights[OptimizationPriority.self_sufficiency],
    ) / RANK_WEIGHTS[-1]
    if w_res / w_cur < 100.0:
        w_res = 100.0 * w_cur
    return w_res, w_cur


def blend_ceiling(
    raw: float, max_a: float, weight: float, mode: BlendMode, priority: OptimizationPriority
) -> float:
    """Blend a factor ceiling by priority weight and factor type."""
    scale = priority_scale(weight, priority)
    if mode == BlendMode.SAVINGS:
        t = min(1.0, max(0.0, scale - 1.0))
        return raw + (max_a - raw) * t
    t = min(1.0, max(0.0, scale))
    return max_a - (max_a - raw) * t


def format_priority_order(
    order: list[OptimizationPriority] | None = None,
    *,
    locale: str | None = None,
) -> str:
    seq = order or DEFAULT_PRIORITY_ORDER
    loc = locale or get_locale()
    return " > ".join(
        t(f"engine.priority.{p.value}", locale=loc) for p in seq
    )
