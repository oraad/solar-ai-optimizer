"""Site timezone helpers for API serialization."""

from __future__ import annotations

from zoneinfo import ZoneInfo

from ..orchestrator import Orchestrator


def site_tz_for(orch: Orchestrator) -> ZoneInfo:
    return orch.forecast.site_tz()
