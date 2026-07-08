"""In-process SolarBackend via SolarOps."""

from __future__ import annotations

from typing import Any

from ...i18n import api_error
from ...i18n.serialize import localize_model, localize_payload
from ...models import Override, utcnow
from ...observability.metrics import metrics
from ...services import SolarOps
from ...orchestrator import Orchestrator
from ..rate_limit import rate_limiter


class OrchestratorBackend:
    """MCP backend using SolarOps in-process."""

    def __init__(self, orch: Orchestrator, *, rate_limit_key: str = "mcp") -> None:
        self._ops = SolarOps(orch)
        self._rate_key = rate_limit_key

    def _check_write_limit(self) -> None:
        if not rate_limiter.allow(self._rate_key, "write"):
            raise api_error("api.debug.rate_limit", 429)

    def _check_read_limit(self) -> None:
        if not rate_limiter.allow(self._rate_key, "read"):
            raise api_error("api.debug.rate_limit", 429)

    async def get_status(self) -> dict[str, Any]:
        self._check_read_limit()
        return localize_model(self._ops.get_status())

    async def get_health(self) -> dict[str, Any]:
        self._check_read_limit()
        status = self._ops.get_status()
        forecast = self._ops.get_forecast()
        fs = self._ops.orch.cfg.fail_safe
        hb = self._ops.orch.heartbeat.last_pulse_at
        from ..config import get_settings

        settings = get_settings()
        return {
            "status": "ok",
            "mcp_enabled": settings.mcp_enabled,
            "ha_connected": status.ha_connected,
            "shadow_mode": status.shadow_mode,
            "paused": status.paused,
            "telemetry_stale": status.telemetry_stale,
            "engine_mode": status.engine_mode,
            "metrics": metrics.as_dict(),
            "time": utcnow().isoformat(),
            "forecast_generated_at": (
                forecast.generated_at.isoformat() if forecast else None
            ),
        }

    async def explain_decision(self, sections: str | None = None) -> dict[str, Any]:
        self._check_read_limit()
        return localize_payload(self._ops.decision_trace(sections=sections))

    async def simulate_decision(self) -> dict[str, Any]:
        if not rate_limiter.allow(self._rate_key, "simulate"):
            raise api_error("api.debug.rate_limit", 429)
        metrics.mcp_simulate_calls_total += 1
        return localize_payload(self._ops.simulate_decision())

    async def get_engine_config(self) -> dict[str, Any]:
        self._check_read_limit()
        return self._ops.get_config()

    async def get_forecast(self) -> dict[str, Any]:
        self._check_read_limit()
        cur = self._ops.get_forecast()
        return localize_model(cur) if cur else {}

    async def get_plan(self) -> dict[str, Any]:
        self._check_read_limit()
        return localize_payload(self._ops.get_plan())

    async def get_grid_stats(self) -> dict[str, Any]:
        self._check_read_limit()
        stats = await self._ops.get_grid_stats()
        return stats.model_dump(mode="json")

    async def get_decision_history(self, limit: int) -> list[dict[str, Any]]:
        self._check_read_limit()
        return localize_payload(await self._ops.history_decisions(limit))

    async def get_execution_history(self, limit: int) -> list[dict[str, Any]]:
        self._check_read_limit()
        return localize_payload(await self._ops.history_executions(limit))

    async def get_shed_history(self, limit: int) -> list[dict[str, Any]]:
        self._check_read_limit()
        return localize_payload(await self._ops.history_shed_executions(limit))

    async def get_telemetry_window(self, hours: int) -> list[dict[str, Any]]:
        self._check_read_limit()
        return await self._ops.history_telemetry(hours)

    async def get_grid_events(self, days: int) -> list[dict[str, Any]]:
        self._check_read_limit()
        return await self._ops.history_grid_events(days)

    async def get_shed_snapshots(self) -> dict[str, Any]:
        self._check_read_limit()
        return self._ops.shed_snapshots()

    async def apply_override(
        self, ov: Override, *, confirm_kill_switch: bool
    ) -> dict[str, Any]:
        self._check_write_limit()
        if ov.kill_switch and not confirm_kill_switch:
            raise api_error("api.override.kill_switch_confirm", 400)
        return localize_payload(await self._ops.apply_override(ov))

    async def clear_override(self) -> dict[str, Any]:
        self._check_write_limit()
        result = self._ops.clear_overrides()
        await self._ops.trigger_cycle()
        return localize_payload(result)

    async def trigger_cycle(self) -> dict[str, Any]:
        self._check_write_limit()
        decision = await self._ops.trigger_cycle()
        return localize_model(decision) if decision else {}

    async def refresh_forecast(self) -> dict[str, Any]:
        self._check_write_limit()
        await self._ops.refresh_forecast()
        cur = self._ops.get_forecast()
        return localize_model(cur) if cur else {}

    async def update_config(self, patch: dict) -> dict[str, Any]:
        self._check_write_limit()
        return await self._ops.update_config(patch)

    async def ask(self, question: str) -> dict[str, Any]:
        self._check_read_limit()
        return localize_payload(await self._ops.assistant_ask(question, apply=False))
