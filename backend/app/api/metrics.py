"""Prometheus text exposition for in-process counters."""

from __future__ import annotations

import hmac

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from ..config import Settings, get_settings
from ..i18n import t
from ..observability.metrics import metrics

metrics_router = APIRouter()


def _metrics_tokens(settings: Settings) -> list[str]:
    """Bearer tokens accepted for /metrics: dedicated METRICS_TOKEN or API_TOKEN."""
    return [tok for tok in (settings.metrics_token, settings.api_token) if tok]


def _metrics_auth_ok(request: Request, settings: Settings) -> bool:
    """Dedicated Bearer check for /metrics (independent of session auth).

    Open when neither METRICS_TOKEN nor API_TOKEN is configured (dev mode);
    the general AuthGateMiddleware still applies its own session-based gate
    when local auth or paired clients are configured.
    """
    tokens = _metrics_tokens(settings)
    if not tokens:
        return True
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return False
    provided = auth[7:].strip()
    return any(hmac.compare_digest(provided, tok) for tok in tokens)


def _prometheus_body(request: Request) -> str:
    m = metrics.as_dict()
    orch = getattr(request.app.state, "orchestrator", None)
    lines = [
        "# HELP process_start_time_seconds Start time of the process since unix epoch.",
        "# TYPE process_start_time_seconds gauge",
        f"process_start_time_seconds {metrics.process_start_time}",
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
    settings = get_settings()
    if not _metrics_auth_ok(request, settings):
        return JSONResponse({"detail": t("api.auth.unauthorized")}, status_code=401)
    return Response(content=_prometheus_body(request), media_type="text/plain; version=0.0.4")
