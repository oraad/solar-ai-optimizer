"""Shared forecast helpers (array sizing, clear-sky expectations)."""

from __future__ import annotations

from ..config import PvArray

CLEAR_SKY_PEAK_SUN_HOURS = 5.0


def total_kwp(arrays: list[PvArray]) -> float:
    return sum(a.kwp for a in arrays) or 1.0


def expected_clear_sky_kwh(total: float) -> float:
    """Rough clear-sky daily yield (kWh) for the installed kWp."""
    return max(1.0, total * CLEAR_SKY_PEAK_SUN_HOURS)
