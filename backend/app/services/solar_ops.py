"""Shared operations layer for REST API and MCP backends."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from pydantic import ValidationError

from ..services.forensics import build_decision_trace, build_simulate_response
from ..models import GridStats, Override, utcnow
from ..storage import repo
from .config_view import config_view

if TYPE_CHECKING:
    from ..orchestrator import Orchestrator


class SolarOps:
    """Thin facade over Orchestrator for API and MCP surfaces."""

    def __init__(self, orch: Orchestrator) -> None:
        self._orch = orch

    @property
    def orch(self) -> Orchestrator:
        return self._orch

    def get_status(self):
        return self._orch.build_status()

    def get_forecast(self):
        return self._orch.forecast.current

    def get_plan(self) -> dict:
        decision = self._orch.latest_decision
        return {
            "decision": decision.model_dump(mode="json") if decision else None,
            "results": [r.model_dump(mode="json") for r in self._orch.latest_results],
            "shed_results": [
                r.model_dump(mode="json") for r in self._orch.latest_shed_results
            ],
            "shadow_mode": self._orch.shadow_mode,
            "paused": self._orch.paused,
        }

    async def get_grid_stats(self) -> GridStats:
        telemetry = self._orch.collector.latest
        live = telemetry.grid_present if telemetry else None
        try:
            return self._orch.latest_grid_stats or await self._orch.reactive.compute_stats(
                live_present=live
            )
        except Exception:
            return GridStats(currently_present=live)

    async def refresh_forecast(self) -> None:
        await self._orch.forecast_cycle()

    async def trigger_cycle(self):
        return await self._orch.control_cycle()

    async def apply_override(self, ov: Override) -> dict:
        return await self._orch.apply_override(ov)

    def clear_overrides(self) -> dict:
        return self._orch.clear_overrides()

    def get_config(self) -> dict:
        return config_view(self._orch.cfg)

    async def update_config(self, patch: dict):
        try:
            cfg = await self._orch.reload_config(patch)
        except ValidationError:
            raise
        return {"ok": True, "config": config_view(cfg)}

    def decision_trace(self, sections: str | None = None) -> dict:
        return build_decision_trace(self._orch, sections=sections)

    def simulate_decision(self) -> dict:
        decision = self._orch.simulate_decision()
        return build_simulate_response(self._orch, decision)

    async def history_telemetry(self, hours: int) -> list:
        since = utcnow() - timedelta(hours=hours)
        rows = await repo.get_telemetry_since(since)
        return [r.model_dump(mode="json") for r in rows]

    async def history_decisions(self, limit: int) -> list[dict]:
        return await repo.get_recent_decisions(limit=limit)

    async def history_executions(self, limit: int) -> list[dict]:
        return await repo.get_recent_executions(limit=limit)

    async def history_shed_executions(self, limit: int) -> list[dict]:
        return await repo.get_recent_shed_executions(limit=limit)

    async def history_grid_events(self, days: int) -> list:
        since = utcnow() - timedelta(days=days)
        events = await repo.get_grid_events_since(since, order="desc")
        return [e.model_dump(mode="json") for e in events]

    def shed_snapshots(self) -> dict:
        snaps = self._orch.snapshot_store.list_all()
        return {
            "snapshots": [
                {
                    "entity": entity,
                    "was_on": snap.was_on,
                    "companion_count": len(snap.companions),
                    "captured_at": snap.captured_at.isoformat(),
                }
                for entity, snap in snaps.items()
            ]
        }
