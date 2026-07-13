"""Status builder: constructs SystemStatus from live Orchestrator state.

Extracted from Orchestrator.build_status so that the status-building logic
can be tested and composed independently of the Orchestrator class.
The Orchestrator keeps a ``build_status()`` facade that delegates here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .models import BatterySummary, ExecutionSummary, SystemStatus, utcnow
from .observability.capabilities import ml_available, mpc_available
from .subsystems import deployment_profile

if TYPE_CHECKING:
    from .orchestrator import Orchestrator


def build_system_status(orch: "Orchestrator") -> SystemStatus:
    """Build a point-in-time SystemStatus snapshot from the orchestrator's live state."""
    telemetry = orch.collector.latest
    stale = _telemetry_stale(orch, telemetry) if telemetry else True

    forecast = orch.forecast.current
    bat = orch.cfg.battery
    return SystemStatus(
        telemetry=telemetry,
        decision=orch.latest_decision,
        execution_summary=(
            orch.latest_execution_summary
            if isinstance(orch.latest_execution_summary, ExecutionSummary)
            else None
        ),
        grid_stats=orch.latest_grid_stats,
        battery_summary=BatterySummary(
            capacity_kwh=bat.capacity_kwh,
            round_trip_efficiency=bat.round_trip_efficiency,
            max_soc_ceiling=bat.max_soc_ceiling,
            min_soc_floor=bat.min_soc_floor,
        ),
        ha_connected=(
            True
            if orch.settings.demo_mode
            else orch.ha.is_reachable(orch.cfg.control.ha_stale_after_seconds)
        ),
        telemetry_stale=stale,
        telemetry_age_seconds=_telemetry_age_seconds(orch),
        forecast_misconfigured=(
            not orch.cfg.site.location_configured and orch.cfg.engine.enabled
        ),
        forecast_degraded=forecast.degraded if forecast else False,
        forecast_provider=orch.forecast.forecast_provider(),
        solcast_configured=orch.forecast.solcast_configured(),
        engine_mode=orch.cfg.engine.mode,
        engine_active="mpc" if orch._mpc is not None else "rules",
        mpc_available=mpc_available(),
        ml_available=ml_available(),
        ml_load_enabled=orch.settings.ml_load_enabled,
        mpc_unavailable=orch.cfg.engine.mode == "mpc" and orch._mpc is None,
        reserve_soc_override=orch.override.reserve_soc,
        force_grid_charge_override=orch.override.force_grid_charge,
        force_shed_off_override=orch.override.force_shed_off,
        shadow_mode=orch.shadow_mode,
        paused=orch.paused,
        shedding_enabled=orch.cfg.load_shedding.enabled,
        grid_charge_enabled=orch.cfg.grid_charge.enabled,
        engine_enabled=orch.cfg.engine.enabled,
        paused_shedding=orch.paused_shedding,
        paused_grid_charge=orch.paused_grid_charge,
        paused_optimization=orch.paused_optimization,
        grid_charge_writes_available=orch._grid_charge_writes_available(),
        deployment_profile=deployment_profile(orch.cfg),
        timezone_config=orch.cfg.site.timezone,
        timezone_resolved=orch.forecast.resolved_timezone,
        last_updated=utcnow(),
    )


def _telemetry_stale(orch: "Orchestrator", telemetry) -> bool:  # noqa: ANN001
    """Delegate to the orchestrator's private helper (keeps one source of truth)."""
    return orch._telemetry_stale(telemetry)


def _telemetry_age_seconds(orch: "Orchestrator") -> float | None:
    """Delegate to the orchestrator's private helper."""
    return orch._telemetry_age_seconds()
