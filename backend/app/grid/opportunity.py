"""Grid present opportunity windows (merge short outages for planning)."""

from __future__ import annotations

from datetime import datetime, timedelta


def merge_opportunity_windows(
    intervals: list[tuple[datetime, datetime, bool]],
    max_outage_ignore_minutes: float,
) -> list[tuple[datetime, datetime]]:
    """Merge present segments separated by short absent gaps into opportunities."""
    present = [(a, b) for a, b, p in intervals if p]
    if not present:
        return []
    tol = max(0.0, float(max_outage_ignore_minutes))
    merged: list[list[datetime]] = [[present[0][0], present[0][1]]]
    for a, b in present[1:]:
        gap_min = (a - merged[-1][1]).total_seconds() / 60.0
        if gap_min <= tol:
            merged[-1][1] = b
        else:
            merged.append([a, b])
    return [(a, b) for a, b in merged]


def avg_opportunity_minutes(
    opportunities: list[tuple[datetime, datetime]],
    *,
    min_minutes: float,
    now: datetime,
    currently_present: bool | None,
) -> float:
    """Mean opportunity duration; drop tiny historical islands (keep live)."""
    if not opportunities:
        return 0.0
    min_m = max(0.0, float(min_minutes))
    durs: list[float] = []
    for a, b in opportunities:
        minutes = (b - a).total_seconds() / 60.0
        is_live = (
            bool(currently_present)
            and b >= now - timedelta(seconds=1)
            and a <= now
        )
        if minutes >= min_m or is_live:
            durs.append(minutes)
    if not durs:
        return 0.0
    return sum(durs) / len(durs)


def present_elapsed_minutes(
    opportunities: list[tuple[datetime, datetime]], now: datetime
) -> float | None:
    """Elapsed minutes since start of the opportunity containing now."""
    for a, b in opportunities:
        if a <= now <= b:
            return max(0.0, (now - a).total_seconds() / 60.0)
    if opportunities:
        a, b = opportunities[-1]
        if b >= now - timedelta(seconds=2) and a <= now:
            return max(0.0, (now - a).total_seconds() / 60.0)
    return None


def trusted_window_minutes(
    *,
    avg_window_minutes: float,
    max_continuous_minutes: float,
    safety_factor: float,
) -> float:
    """Trusted opportunity length with cold-start prior and safety derating."""
    max_c = max(0.0, float(max_continuous_minutes))
    safety = max(0.0, min(1.0, float(safety_factor)))
    avg = max(0.0, float(avg_window_minutes))
    base = min(avg, max_c) if avg > 0 else max_c
    return base * safety
