"""FastMCP server factory and tool registration."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations

from ..models import Override
from ..observability.metrics import metrics
from .audit import audit_tool_call
from .backend import SolarBackend
from .prompts import register_prompts

log = logging.getLogger("mcp.server")

GetBackend = Callable[[], SolarBackend | Awaitable[SolarBackend]]


def create_mcp_server(get_backend: GetBackend, *, transport: str = "stdio") -> FastMCP:
    # Bearer auth already gates HTTP; disable Host-header DNS-rebinding checks so
    # LAN IPs and TestClient ("testserver") are not rejected with HTTP 421.
    mcp = FastMCP(
        "solar-ai-optimizer",
        instructions=(
            "Read-only by default. Mutating tools require admin bearer token. "
            "Start troubleshooting with solar_explain_decision."
        ),
        stateless_http=True,
        json_response=True,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=False,
        ),
    )

    async def be() -> SolarBackend:
        result = get_backend()
        if isinstance(result, Awaitable):
            return await result
        return result

    def _ro() -> ToolAnnotations:
        return ToolAnnotations(readOnlyHint=True, openWorldHint=False)

    def _write(*, destructive: bool = False, idempotent: bool = True) -> ToolAnnotations:
        return ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=destructive,
            idempotentHint=idempotent,
            openWorldHint=False,
        )

    async def _call(tool: str, coro: Awaitable[Any]) -> Any:
        metrics.mcp_tool_calls_total += 1
        with audit_tool_call(tool, transport=transport) as audit:
            try:
                return await coro
            except Exception:
                audit["error"] = True
                raise

    @mcp.tool(name="solar_get_status", annotations=_ro())
    async def solar_get_status() -> dict[str, Any]:
        """Return live optimizer status: telemetry, decision, shadow mode, HA health."""
        b = await be()
        return await _call("solar_get_status", b.get_status())

    @mcp.tool(name="solar_explain_decision", annotations=_ro())
    async def solar_explain_decision(sections: str | None = None) -> dict[str, Any]:
        """Full decision forensics: inputs, engine context, reasoning, execution gaps."""
        b = await be()
        return await _call("solar_explain_decision", b.explain_decision(sections))

    @mcp.tool(name="solar_simulate_decision", annotations=_ro())
    async def solar_simulate_decision() -> dict[str, Any]:
        """Dry-run decision using cached telemetry; does not apply writes."""
        b = await be()
        return await _call("solar_simulate_decision", b.simulate_decision())

    @mcp.tool(name="solar_get_engine_config", annotations=_ro())
    async def solar_get_engine_config() -> dict[str, Any]:
        """Effective engine, reserve, and battery config (secrets redacted)."""
        b = await be()
        return await _call("solar_get_engine_config", b.get_engine_config())

    @mcp.tool(name="solar_get_forecast", annotations=_ro())
    async def solar_get_forecast() -> dict[str, Any]:
        """Current solar/load forecast bundle."""
        b = await be()
        return await _call("solar_get_forecast", b.get_forecast())

    @mcp.tool(name="solar_get_plan", annotations=_ro())
    async def solar_get_plan() -> dict[str, Any]:
        """Latest decision plan and execution results."""
        b = await be()
        return await _call("solar_get_plan", b.get_plan())

    @mcp.tool(name="solar_get_grid_stats", annotations=_ro())
    async def solar_get_grid_stats() -> dict[str, Any]:
        """Grid uptime and transition statistics."""
        b = await be()
        return await _call("solar_get_grid_stats", b.get_grid_stats())

    @mcp.tool(name="solar_get_decision_history", annotations=_ro())
    async def solar_get_decision_history(limit: int = 100) -> list[dict[str, Any]]:
        """Recent decision audit rows with reserve rationales."""
        b = await be()
        return await _call("solar_get_decision_history", b.get_decision_history(limit))

    @mcp.tool(name="solar_get_execution_history", annotations=_ro())
    async def solar_get_execution_history(limit: int = 100) -> list[dict[str, Any]]:
        """Inverter write outcomes and skipped_reason patterns."""
        b = await be()
        return await _call("solar_get_execution_history", b.get_execution_history(limit))

    @mcp.tool(name="solar_get_shed_history", annotations=_ro())
    async def solar_get_shed_history(limit: int = 100) -> list[dict[str, Any]]:
        """Load-shed tier execution history."""
        b = await be()
        return await _call("solar_get_shed_history", b.get_shed_history(limit))

    @mcp.tool(name="solar_get_telemetry_window", annotations=_ro())
    async def solar_get_telemetry_window(hours: int = 24) -> list[dict[str, Any]]:
        """Telemetry samples for correlating decisions with SOC/load/PV."""
        b = await be()
        return await _call("solar_get_telemetry_window", b.get_telemetry_window(hours))

    @mcp.tool(name="solar_get_grid_events", annotations=_ro())
    async def solar_get_grid_events(days: int = 7) -> list[dict[str, Any]]:
        """Grid presence transition events."""
        b = await be()
        return await _call("solar_get_grid_events", b.get_grid_events(days))

    @mcp.tool(name="solar_get_shed_snapshots", annotations=_ro())
    async def solar_get_shed_snapshots() -> dict[str, Any]:
        """Pending shed restore snapshots."""
        b = await be()
        return await _call("solar_get_shed_snapshots", b.get_shed_snapshots())

    @mcp.tool(name="solar_apply_override", annotations=_write(destructive=False))
    async def solar_apply_override(
        shadow_mode: bool | None = None,
        force_grid_charge: bool | None = None,
        force_shed_off: bool | None = None,
        reserve_soc: float | None = None,
        pause_engine: bool | None = None,
        pause_shedding: bool | None = None,
        pause_grid_charge: bool | None = None,
        pause_optimization: bool | None = None,
        kill_switch: bool | None = None,
        confirm_kill_switch: bool = False,
    ) -> dict[str, Any]:
        """Apply operator override. confirm_kill_switch required when kill_switch is true."""
        ov = Override(
            shadow_mode=shadow_mode,
            force_grid_charge=force_grid_charge,
            force_shed_off=force_shed_off,
            reserve_soc=reserve_soc,
            pause_engine=pause_engine,
            pause_shedding=pause_shedding,
            pause_grid_charge=pause_grid_charge,
            pause_optimization=pause_optimization,
            kill_switch=kill_switch,
        )
        b = await be()
        return await _call(
            "solar_apply_override",
            b.apply_override(ov, confirm_kill_switch=confirm_kill_switch),
        )

    @mcp.tool(name="solar_clear_override", annotations=_write())
    async def solar_clear_override() -> dict[str, Any]:
        """Clear operator overrides and run a control cycle."""
        b = await be()
        return await _call("solar_clear_override", b.clear_override())

    @mcp.tool(name="solar_trigger_cycle", annotations=_write(idempotent=False))
    async def solar_trigger_cycle() -> dict[str, Any]:
        """Run a full control cycle (applies writes unless shadow mode)."""
        b = await be()
        return await _call("solar_trigger_cycle", b.trigger_cycle())

    @mcp.tool(name="solar_refresh_forecast", annotations=_write())
    async def solar_refresh_forecast() -> dict[str, Any]:
        """Refresh solar/load forecast."""
        b = await be()
        return await _call("solar_refresh_forecast", b.refresh_forecast())

    @mcp.tool(name="solar_update_config", annotations=_write())
    async def solar_update_config(patch: dict) -> dict[str, Any]:
        """Partial config update (deep-merge). Read config first."""
        b = await be()
        return await _call("solar_update_config", b.update_config(patch))

    @mcp.tool(name="solar_ask", annotations=_ro())
    async def solar_ask(question: str) -> dict[str, Any]:
        """Natural-language Q&A via local LLM (read-only; apply=false)."""
        b = await be()
        return await _call("solar_ask", b.ask(question[:2000]))

    register_prompts(mcp)
    return mcp
