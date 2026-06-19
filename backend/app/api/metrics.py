"""Prometheus text exposition for in-process counters."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response

from ..observability.metrics import metrics

metrics_router = APIRouter()


def _prometheus_body(request: Request) -> str:
    m = metrics.as_dict()
    orch = getattr(request.app.state, "orchestrator", None)
    lines = [
        "# HELP solar_control_cycles_total Control evaluation cycles completed.",
        "# TYPE solar_control_cycles_total counter",
        f"solar_control_cycles_total {m['control_cycles']}",
        "# HELP solar_control_cycle_failures_total Telemetry failures in control cycle.",
        "# TYPE solar_control_cycle_failures_total counter",
        f"solar_control_cycle_failures_total {m['control_cycle_failures']}",
        "# HELP solar_executor_writes_applied_total Inverter writes applied.",
        "# TYPE solar_executor_writes_applied_total counter",
        f"solar_executor_writes_applied_total {m['executor_writes_applied']}",
        "# HELP solar_executor_writes_skipped_total Inverter writes skipped.",
        "# TYPE solar_executor_writes_skipped_total counter",
        f"solar_executor_writes_skipped_total {m['executor_writes_skipped']}",
        "# HELP solar_shed_writes_applied_total Shed switch writes applied.",
        "# TYPE solar_shed_writes_applied_total counter",
        f"solar_shed_writes_applied_total {m['shed_writes_applied']}",
        "# HELP solar_shed_writes_skipped_total Shed switch writes skipped.",
        "# TYPE solar_shed_writes_skipped_total counter",
        f"solar_shed_writes_skipped_total {m['shed_writes_skipped']}",
        "# HELP solar_forecast_refresh_failures_total Forecast refresh failures.",
        "# TYPE solar_forecast_refresh_failures_total counter",
        f"solar_forecast_refresh_failures_total {m['forecast_refresh_failures']}",
        "# HELP solar_mpc_fallbacks_total MPC decide fallbacks to rules engine.",
        "# TYPE solar_mpc_fallbacks_total counter",
        f"solar_mpc_fallbacks_total {m['mpc_fallbacks']}",
        "# HELP solar_ha_ws_restarts_total HA WebSocket stream restarts.",
        "# TYPE solar_ha_ws_restarts_total counter",
        f"solar_ha_ws_restarts_total {m['ha_ws_restarts']}",
    ]
    if orch is not None:
        status = orch.build_status()
        lines.extend(
            [
                "# HELP solar_telemetry_stale 1 when telemetry snapshot is stale.",
                "# TYPE solar_telemetry_stale gauge",
                f"solar_telemetry_stale {1 if status.telemetry_stale else 0}",
                "# HELP solar_ha_connected 1 when Home Assistant was reached recently.",
                "# TYPE solar_ha_connected gauge",
                f"solar_ha_connected {1 if status.ha_connected else 0}",
            ]
        )
    return "\n".join(lines) + "\n"


@metrics_router.get("/metrics")
async def prometheus_metrics(request: Request) -> Response:
    return Response(content=_prometheus_body(request), media_type="text/plain; version=0.0.4")
