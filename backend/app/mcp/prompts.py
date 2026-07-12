"""Reusable MCP prompts for agent troubleshooting playbooks."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP


def register_prompts(mcp: FastMCP) -> None:
    @mcp.prompt(name="solar_explain_last_decision")
    def solar_explain_last_decision() -> str:
        return (
            "Troubleshoot the latest optimizer decision:\n"
            "1. Call solar_explain_decision (include causality + execution).\n"
            "2. Compare intended vs applied for reserve % and grid-charge amps.\n"
            "3. Check causality.explanation.reserve.source (rules|mpc|operator).\n"
            "4. Call solar_get_engine_config if reserve or priorities look wrong.\n"
            "5. Call solar_get_decision_history / executions with cycle_id if needed.\n"
            "Do not apply overrides without explicit user confirmation.\n"
            "Note: paused_optimization does not stop planning; only write pauses block actuators."
        )

    @mcp.prompt(name="solar_grid_outage_triage")
    def solar_grid_outage_triage() -> str:
        return (
            "Grid outage triage:\n"
            "1. solar_get_status and solar_get_grid_stats.\n"
            "2. solar_get_grid_events for recent transitions.\n"
            "3. solar_get_shed_snapshots for pending restores.\n"
            "Read-only unless the user confirms a mutating tool."
        )

    @mcp.prompt(name="solar_debug_reserve_high")
    def solar_debug_reserve_high() -> str:
        return (
            "Reserve SOC too high checklist:\n"
            "1. solar_explain_decision — compare solar_bridge_soc vs autonomy_floor_soc.\n"
            "2. Check forecast degraded_reasons and cloudy_tomorrow.\n"
            "3. solar_get_engine_config — reserve buffers and priority_order.\n"
            "4. solar_simulate_decision after config tweaks (no live writes)."
        )
