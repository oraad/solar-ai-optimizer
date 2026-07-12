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


def grid_present_risk_multiplier(
    resilience_weight: float, savings_weight: float
) -> float:
    """Replace hardcoded 0.5 grid-present risk discount; 0.5 at default ranks."""
    pivot_r, pivot_s = RANK_WEIGHTS[0], RANK_WEIGHTS[1]
    mult = 0.5
    mult += 0.15 * (pivot_r - resilience_weight) / (pivot_r - RANK_WEIGHTS[-1])
    mult -= 0.10 * (savings_weight - pivot_s) / (1.0 - pivot_s)
    return max(0.35, min(0.65, mult))


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
