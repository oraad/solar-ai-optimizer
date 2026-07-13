"""REST endpoints for status, forecasts, plan, history, config, and overrides."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, ValidationError

from .. import __version__
from ..auth.install_id import get_or_create_install_id
from ..i18n import api_error, format_validation_errors, t
from ..i18n.serialize import localize_model, localize_payload, serialize_api_payload
from ..config import LoadSheddingConfig
from ..models import GridStats, Override, utcnow
from ..orchestrator import Orchestrator
from ..storage import repo
from .session import SessionUser, assert_override_allowed, require_admin, require_authenticated
from .timezone import site_tz_for

log = logging.getLogger("api.routes")

router = APIRouter(prefix="/api", tags=["solar"])

RequireSession = Depends(require_authenticated)


def _orch(request: Request) -> Orchestrator:
    return request.app.state.orchestrator


def _loc(model, site_tz: ZoneInfo) -> dict:  # noqa: ANN001
    return localize_model(model, site_tz=site_tz)


def _loc_data(data: dict | list, site_tz: ZoneInfo) -> dict | list:
    return localize_payload(data, site_tz=site_tz)


def _dump(data, site_tz: ZoneInfo):  # noqa: ANN001
    return serialize_api_payload(data, site_tz=site_tz)


def _parse_cursor(cursor: str | None) -> datetime | None:
    """Decode an opaque history cursor (an ISO row timestamp) for keyset paging."""
    if not cursor:
        return None
    try:
        return datetime.fromisoformat(cursor.replace("Z", "+00:00"))
    except ValueError:
        return None


class HealthResponse(BaseModel):
    """Contract for GET /api/health. Extra diagnostic fields are passed through."""

    model_config = ConfigDict(extra="allow")

    status: str
    version: str
    install_id: str
    ha_connected: bool
    shadow_mode: bool
    paused: bool
    telemetry_stale: bool
    engine_mode: str
    engine_active: str


@router.get("/ping")
async def ping() -> dict:
    """Cheap, unauthenticated liveness probe (load balancers, HA add-on watchdog)."""
    return {"ok": True}


@router.get("/me")
async def me(
    request: Request,
    session: SessionUser = RequireSession,
) -> dict:
    from ..config import get_settings

    return session.to_me_dict(get_settings())


@router.get("/health")
async def health(request: Request) -> dict:
    from ..config import get_settings
    from ..observability.metrics import metrics

    orch = _orch(request)
    settings = get_settings()
    status = orch.build_status()
    forecast = orch.forecast.current
    hb = orch.heartbeat.last_pulse_at
    mcp_path = settings.mcp_http_path.rstrip("/") or "/mcp"
    # Live mount truth (not settings inference — static "/" used to swallow /mcp).
    mcp_http_mounted = getattr(request.app.state, "mcp_server", None) is not None
    mcp_http_url = None
    if mcp_http_mounted:
        mcp_http_url = f"{str(request.base_url).rstrip('/')}{mcp_path}"
    payload = HealthResponse.model_validate(
        {
            "status": "ok",
            "install_id": get_or_create_install_id(settings.data_dir),
            "version": __version__,
            "mcp_enabled": settings.mcp_enabled,
            "mcp_http_path": mcp_path,
            "mcp_auth_configured": settings.mcp_auth_configured,
            "mcp_http_mounted": mcp_http_mounted,
            "mcp_http_url": mcp_http_url,
            "mcp_tool_calls_total": metrics.mcp_tool_calls_total,
            "mcp_auth_failures_total": metrics.mcp_auth_failures_total,
            "is_addon": settings.is_addon,
            "ha_connected": status.ha_connected,
            **orch.ha_connection_diagnostics(),
            "shadow_mode": status.shadow_mode,
            "paused": status.paused,
            "telemetry_stale": status.telemetry_stale,
            "telemetry_age_seconds": status.telemetry_age_seconds,
            "forecast_misconfigured": status.forecast_misconfigured,
            "forecast_degraded": status.forecast_degraded,
            "engine_mode": status.engine_mode,
            "engine_active": status.engine_active,
            "heartbeat_configured": True,
            "heartbeat_last_pulse": hb.isoformat() if hb else None,
            "metrics": metrics.as_dict(),
            "time": utcnow().isoformat(),
            "timezone_config": status.timezone_config,
            "timezone_resolved": status.timezone_resolved,
            "forecast_generated_at": (
                forecast.generated_at.isoformat() if forecast else None
            ),
        }
    )
    return _dump(payload.model_dump(mode="json"), site_tz_for(orch))


@router.post("/ha/retry-connection")
async def ha_retry_connection(
    request: Request,
    _admin: SessionUser = Depends(require_admin),
) -> dict:
    """Close the HA WebSocket circuit breaker and retry connectivity."""
    orch = _orch(request)
    return await orch.retry_ha_connection()


@router.get("/status")
async def status(
    request: Request,
    _session: SessionUser = RequireSession,
) -> dict:
    orch = _orch(request)
    return _loc(orch.build_status(), site_tz_for(orch))


@router.get("/forecast")
async def forecast(
    request: Request,
    _session: SessionUser = RequireSession,
) -> dict:
    orch = _orch(request)
    tz = site_tz_for(orch)
    cur = orch.forecast.current
    return _loc(cur, tz) if cur else {}


@router.post("/forecast/refresh")
async def forecast_refresh(
    request: Request,
    _admin: SessionUser = Depends(require_admin),
) -> dict:
    orch = _orch(request)
    tz = site_tz_for(orch)
    await orch.forecast_cycle()
    cur = orch.forecast.current
    return _loc(cur, tz) if cur else {}


@router.get("/plan")
async def plan(
    request: Request,
    _session: SessionUser = RequireSession,
) -> dict:
    orch = _orch(request)
    tz = site_tz_for(orch)
    decision = orch.latest_decision
    return _loc_data(
        {
            "cycle_id": decision.cycle_id if decision else None,
            "decision": decision.model_dump(mode="json") if decision else None,
            "results": [r.model_dump(mode="json") for r in orch.latest_results],
            "shed_results": [
                r.model_dump(mode="json") for r in orch.latest_shed_results
            ],
            "execution_summary": (
                orch.latest_execution_summary.model_dump(mode="json")
                if orch.latest_execution_summary
                else None
            ),
            "shadow_mode": orch.shadow_mode,
            "paused": orch.paused,
        },
        tz,
    )


@router.post("/cycle")
async def force_cycle(
    request: Request,
    _admin: SessionUser = Depends(require_admin),
) -> dict:
    orch = _orch(request)
    decision = await orch.control_cycle()
    return _loc(decision, site_tz_for(orch)) if decision else {}


@router.get("/grid-stats")
async def grid_stats(
    request: Request,
    _session: SessionUser = RequireSession,
) -> dict:
    orch = _orch(request)
    tz = site_tz_for(orch)
    telemetry = orch.collector.latest
    live = telemetry.grid_present if telemetry else None
    try:
        stats = orch.latest_grid_stats or await orch.reactive.compute_stats(
            live_present=live
        )
    except Exception:
        log.warning("grid-stats endpoint failed", exc_info=True)
        stats = GridStats(currently_present=live)
    return _dump(stats.model_dump(mode="json"), tz)


@router.get("/history/telemetry")
async def history_telemetry(
    request: Request,
    hours: int = Query(default=24, ge=1, le=720),
    _session: SessionUser = RequireSession,
) -> list[dict]:
    orch = _orch(request)
    tz = site_tz_for(orch)
    since = utcnow() - timedelta(hours=hours)
    rows = await repo.get_telemetry_since(since)
    return _dump([r.model_dump(mode="json") for r in rows], tz)


@router.get("/history/decisions")
async def history_decisions(
    request: Request,
    limit: int = Query(default=100, ge=1, le=1000),
    cycle_id: str | None = Query(default=None),
    cursor: str | None = Query(default=None),
    _session: SessionUser = RequireSession,
) -> dict:
    orch = _orch(request)
    before = _parse_cursor(cursor)
    if cycle_id:
        rows = await repo.get_decisions_by_cycle_id(cycle_id, limit=limit, before=before)
    else:
        rows = await repo.get_recent_decisions(limit=limit, before=before)
    next_cursor = rows[-1]["ts"] if len(rows) >= limit else None
    return {
        "items": localize_payload(rows, site_tz=site_tz_for(orch)),
        "next_cursor": next_cursor,
    }


@router.get("/history/grid-events")
async def history_grid_events(
    request: Request,
    days: int = Query(default=7, ge=1, le=90),
    _session: SessionUser = RequireSession,
) -> list[dict]:
    orch = _orch(request)
    tz = site_tz_for(orch)
    since = utcnow() - timedelta(days=days)
    events = await repo.get_grid_events_since(since, order="desc")
    return _dump([e.model_dump(mode="json") for e in events], tz)


from ..services.config_view import config_view
def _shedding_entity_ids(load_shedding: LoadSheddingConfig) -> set[str]:
    ids: set[str] = set()
    for tier in load_shedding.tiers:
        ids.update(tier.entity_ids())
        for companions in tier.state_entities.values():
            ids.update(c.strip() for c in companions if c and str(c).strip())
    return ids


def _entity_info_from_state(state: dict) -> dict | None:
    eid = state.get("entity_id")
    if not eid:
        return None
    dom = eid.split(".", 1)[0]
    name = (state.get("attributes") or {}).get("friendly_name") or eid
    return {"entity_id": eid, "name": name, "domain": dom}


async def _entity_infos_for_ids(orch: Orchestrator, wanted_ids: set[str]) -> tuple[bool, list[dict]]:
    connected = orch.ha.is_reachable(orch.cfg.control.ha_stale_after_seconds)
    if not wanted_ids:
        return connected, []

    states_by_id: dict[str, dict] = {}
    try:
        states = await orch.ha.get_states()
        for s in states:
            eid = s.get("entity_id")
            if eid in wanted_ids:
                states_by_id[eid] = s
    except Exception:  # noqa: BLE001 - HA may be unreachable
        return False, []

    out: list[dict] = []
    for eid in sorted(wanted_ids):
        state = states_by_id.get(eid)
        if state:
            info = _entity_info_from_state(state)
            if info:
                out.append(info)
        else:
            out.append({"entity_id": eid, "name": eid, "domain": eid.split(".", 1)[0]})
    return connected, out


@router.get("/entities")
async def entities(
    request: Request,
    domain: str | None = Query(default=None),
    _admin: SessionUser = Depends(require_admin),
) -> dict:
    """List Home Assistant entities for UI autocomplete.

    Optional `domain` filter is a comma-separated list, e.g. "sensor,switch".
    Returns {connected, entities:[{entity_id, name, domain}]}.
    """
    orch = _orch(request)
    wanted = {d.strip() for d in domain.split(",") if d.strip()} if domain else None
    try:
        states = await orch.ha.get_states()
    except Exception:  # noqa: BLE001 - HA may be unreachable; return empty list
        return {"connected": False, "entities": []}

    out: list[dict] = []
    for s in states:
        eid = s.get("entity_id")
        if not eid:
            continue
        dom = eid.split(".", 1)[0]
        if wanted and dom not in wanted:
            continue
        name = (s.get("attributes") or {}).get("friendly_name") or eid
        out.append({"entity_id": eid, "name": name, "domain": dom})
    out.sort(key=lambda e: e["entity_id"])
    return {
        "connected": orch.ha.is_reachable(orch.cfg.control.ha_stale_after_seconds),
        "entities": out,
    }


@router.get("/shed/device-companions")
async def shed_device_companions(
    request: Request,
    entity: str = Query(..., min_length=3),
    _admin: SessionUser = Depends(require_admin),
) -> dict:
    """Discover actionable companion entities on the same HA device as a power entity."""
    from ..ha.device_discovery import discover_device_companions

    orch = _orch(request)
    try:
        result = await discover_device_companions(orch.ha, entity, use_cache=False)
    except Exception as e:  # noqa: BLE001
        return {
            "power_entity": entity,
            "device_id": None,
            "companions": [],
            "warning": str(e),
        }
    return _loc_data(
        {
            "power_entity": result.power_entity,
            "device_id": result.device_id,
            "companions": [c.model_dump() for c in result.companions],
            "warning": result.warning,
        },
        site_tz_for(orch),
    )


@router.get("/shed/snapshots")
async def shed_snapshots(
    request: Request,
    _admin: SessionUser = Depends(require_admin),
) -> dict:
    """Pending shed snapshots (debug / operator visibility)."""
    orch = _orch(request)
    tz = site_tz_for(orch)
    snaps = orch.snapshot_store.list_all()
    return _dump(
        {
            "snapshots": [
                {
                    "entity": entity,
                    "was_on": snap.was_on,
                    "companion_count": len(snap.companions),
                    "captured_at": snap.captured_at.isoformat(),
                }
                for entity, snap in snaps.items()
            ]
        },
        tz,
    )


@router.get("/config")
async def get_config(
    request: Request,
    _admin: SessionUser = Depends(require_admin),
) -> dict:
    """Full (non-secret) effective config surfaced to the dashboard for editing."""
    return config_view(_orch(request).cfg)


@router.get("/config/load-shedding")
async def get_load_shedding_config(
    request: Request,
    _session: SessionUser = Depends(require_authenticated),
) -> dict:
    """Read-only load shedding config for viewer dashboard tab."""
    orch = _orch(request)
    load_shedding = orch.cfg.load_shedding
    wanted = _shedding_entity_ids(load_shedding)
    connected, entity_list = await _entity_infos_for_ids(orch, wanted)
    return {
        "load_shedding": load_shedding.model_dump(),
        "entities": entity_list,
        "connected": connected,
    }


@router.put("/config")
async def put_config(
    request: Request,
    patch: dict = Body(...),
    admin: SessionUser = Depends(require_admin),
) -> dict:
    """Apply a partial config update from the UI (deep-merged + persisted)."""
    orch = _orch(request)
    actor = admin.user_id or admin.username or "unknown"
    try:
        cfg = await orch.reload_config(patch)
    except ValidationError as e:
        log.warning(
            "Config update REJECTED by actor=%s mode=%s fields=%s: %s",
            actor,
            admin.auth_mode,
            list(patch.keys()),
            e,
        )
        raise HTTPException(
            status_code=422, detail=format_validation_errors(e.errors())
        ) from e
    except Exception as e:  # noqa: BLE001 - surface validation errors to the UI
        log.warning(
            "Config update REJECTED by actor=%s mode=%s fields=%s: %s",
            actor,
            admin.auth_mode,
            list(patch.keys()),
            e,
        )
        detail = str(e)
        if detail.startswith("api.config."):
            raise HTTPException(status_code=422, detail=t(detail)) from e
        raise HTTPException(status_code=422, detail=detail) from e
    log.info(
        "Config update by actor=%s mode=%s fields=%s",
        actor,
        admin.auth_mode,
        list(patch.keys()),
    )
    return {"ok": True, "config": config_view(cfg)}


@router.post("/config/reset")
async def reset_config(
    request: Request,
    _admin: SessionUser = Depends(require_admin),
) -> dict:
    cfg = await _orch(request).reset_config()
    return {"ok": True, "config": config_view(cfg)}


@router.get("/model/export")
async def model_export(
    request: Request,
    _admin: SessionUser = Depends(require_admin),
) -> dict:
    """Export the learned model (bias factors + load profile) as JSON."""
    return _orch(request).forecast.export_model()


@router.post("/model/import")
async def model_import(
    request: Request,
    data: dict = Body(...),
    _admin: SessionUser = Depends(require_admin),
) -> dict:
    orch = _orch(request)
    try:
        async with orch.forecast._refresh_lock:
            orch.forecast.import_model(data)
            orch.forecast.save_model(orch.model_path)
        await orch.forecast_cycle()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=422, detail=str(e)) from e
    return {"ok": True, "ml_import_locked": orch.forecast.ml_import_locked}


@router.post("/model/retrain")
async def model_retrain(
    request: Request,
    _admin: SessionUser = Depends(require_admin),
) -> dict:
    orch = _orch(request)
    trained = await orch.forecast.retrain_ml_load()
    orch.forecast.save_model(orch.model_path)
    await orch.forecast_cycle()
    return {
        "ok": True,
        "trained": trained,
        "ml_import_locked": orch.forecast.ml_import_locked,
    }


class OverrideRequest(Override):
    """REST override body; kill_switch requires confirm=true."""

    confirm: bool = False


@router.post("/override")
async def post_override(
    request: Request,
    body: OverrideRequest,
    session: SessionUser = Depends(require_authenticated),
) -> dict:
    if body.kill_switch and not body.confirm:
        raise api_error("api.override.kill_switch_confirm", 400)
    ov = Override(**body.model_dump(exclude={"confirm"}))
    if not ov.model_dump(exclude_none=True):
        raise api_error("api.override.no_fields", 400)
    assert_override_allowed(session, ov)
    touched = list(ov.model_dump(exclude_none=True).keys())
    log.info(
        "Override by user=%s mode=%s fields=%s",
        session.user_id or session.username or "unknown",
        session.auth_mode,
        touched,
    )
    return localize_payload(
        await _orch(request).apply_override(ov),
        site_tz=site_tz_for(_orch(request)),
    )


@router.post("/override/clear")
async def clear_override(
    request: Request,
    _admin: SessionUser = Depends(require_admin),
) -> dict:
    orch = _orch(request)
    result = orch.clear_overrides()
    await orch.control_cycle()
    return localize_payload(result, site_tz=site_tz_for(orch))


@router.get("/history/executions")
async def history_executions(
    request: Request,
    limit: int = Query(default=100, ge=1, le=1000),
    cycle_id: str | None = Query(default=None),
    cursor: str | None = Query(default=None),
    _session: SessionUser = RequireSession,
) -> dict:
    rows = await repo.get_recent_executions(
        limit=limit, cycle_id=cycle_id, before=_parse_cursor(cursor)
    )
    next_cursor = rows[-1]["ts"] if len(rows) >= limit else None
    return {
        "items": localize_payload(rows, site_tz=site_tz_for(_orch(request))),
        "next_cursor": next_cursor,
    }


@router.get("/history/shed-executions")
async def history_shed_executions(
    request: Request,
    limit: int = Query(default=100, ge=1, le=1000),
    cycle_id: str | None = Query(default=None),
    cursor: str | None = Query(default=None),
    _session: SessionUser = RequireSession,
) -> dict:
    rows = await repo.get_recent_shed_executions(
        limit=limit, cycle_id=cycle_id, before=_parse_cursor(cursor)
    )
    next_cursor = rows[-1]["ts"] if len(rows) >= limit else None
    return {
        "items": localize_payload(rows, site_tz=site_tz_for(_orch(request))),
        "next_cursor": next_cursor,
    }
