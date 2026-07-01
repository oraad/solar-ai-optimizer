"""REST endpoints for status, forecasts, plan, history, config, and overrides."""

from __future__ import annotations

import logging
from datetime import timedelta

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ValidationError

from ..i18n import api_error, format_validation_errors, t
from ..i18n.serialize import localize_model, localize_payload
from ..llm.assistant import Assistant
from ..models import GridStats, Override, utcnow
from ..orchestrator import Orchestrator
from ..storage import repo
from .session import SessionUser, assert_override_allowed, get_session, require_admin, require_authenticated

log = logging.getLogger("api.routes")

router = APIRouter(prefix="/api", tags=["solar"])


def _orch(request: Request) -> Orchestrator:
    return request.app.state.orchestrator


def _loc(model) -> dict:  # noqa: ANN001
    return localize_model(model)


def _loc_data(data: dict | list) -> dict | list:
    return localize_payload(data)


@router.get("/me")
async def me(request: Request) -> dict:
    from ..config import get_settings

    settings = get_settings()
    session = get_session(request)
    if not session.authenticated and (
        settings.local_auth_enabled or settings.api_token
    ):
        raise api_error("api.auth.unauthorized", 401)
    return session.to_me_dict(settings)


@router.get("/health")
async def health(request: Request) -> dict:
    from ..observability.metrics import metrics

    orch = _orch(request)
    status = orch.build_status()
    forecast = orch.forecast.current
    fs = orch.cfg.fail_safe
    hb = orch.heartbeat.last_pulse_at
    return {
        "status": "ok",
        "ha_connected": status.ha_connected,
        "shadow_mode": status.shadow_mode,
        "paused": status.paused,
        "telemetry_stale": status.telemetry_stale,
        "telemetry_age_seconds": status.telemetry_age_seconds,
        "forecast_misconfigured": status.forecast_misconfigured,
        "forecast_degraded": status.forecast_degraded,
        "engine_mode": status.engine_mode,
        "engine_active": status.engine_active,
        "heartbeat_configured": bool(
            fs.heartbeat_enabled and fs.heartbeat_entity
        ),
        "heartbeat_last_pulse": hb.isoformat() if hb else None,
        "metrics": metrics.as_dict(),
        "time": utcnow().isoformat(),
        "timezone_config": status.timezone_config,
        "timezone_resolved": status.timezone_resolved,
        "forecast_generated_at": (
            forecast.generated_at.isoformat() if forecast else None
        ),
    }


@router.get("/status")
async def status(request: Request) -> dict:
    return _loc(_orch(request).build_status())


@router.get("/forecast")
async def forecast(request: Request) -> dict:
    cur = _orch(request).forecast.current
    return _loc(cur) if cur else {}


@router.post("/forecast/refresh")
async def forecast_refresh(
    request: Request,
    _admin: SessionUser = Depends(require_admin),
) -> dict:
    orch = _orch(request)
    await orch.forecast_cycle()
    cur = orch.forecast.current
    return _loc(cur) if cur else {}


@router.get("/plan")
async def plan(request: Request) -> dict:
    orch = _orch(request)
    decision = orch.latest_decision
    return _loc_data(
        {
            "decision": decision.model_dump(mode="json") if decision else None,
            "results": [r.model_dump(mode="json") for r in orch.latest_results],
            "shed_results": [
                r.model_dump(mode="json") for r in orch.latest_shed_results
            ],
            "shadow_mode": orch.shadow_mode,
            "paused": orch.paused,
        }
    )


@router.post("/cycle")
async def force_cycle(
    request: Request,
    _admin: SessionUser = Depends(require_admin),
) -> dict:
    decision = await _orch(request).control_cycle()
    return _loc(decision) if decision else {}


@router.get("/grid-stats")
async def grid_stats(request: Request) -> dict:
    orch = _orch(request)
    telemetry = orch.collector.latest
    live = telemetry.grid_present if telemetry else None
    try:
        stats = orch.latest_grid_stats or await orch.reactive.compute_stats(
            live_present=live
        )
    except Exception:
        log.warning("grid-stats endpoint failed", exc_info=True)
        stats = GridStats(currently_present=live)
    return stats.model_dump(mode="json")


@router.get("/history/telemetry")
async def history_telemetry(
    request: Request, hours: int = Query(default=24, ge=1, le=720)
) -> list[dict]:
    since = utcnow() - timedelta(hours=hours)
    rows = await repo.get_telemetry_since(since)
    return [r.model_dump(mode="json") for r in rows]


@router.get("/history/decisions")
async def history_decisions(
    request: Request, limit: int = Query(default=100, ge=1, le=1000)
) -> list[dict]:
    rows = await repo.get_recent_decisions(limit=limit)
    return localize_payload(rows)  # type: ignore[return-value]


@router.get("/history/grid-events")
async def history_grid_events(
    request: Request, days: int = Query(default=7, ge=1, le=90)
) -> list[dict]:
    since = utcnow() - timedelta(days=days)
    events = await repo.get_grid_events_since(since, order="desc")
    return [e.model_dump(mode="json") for e in events]


def _config_view(cfg) -> dict:
    """Serialise config for the UI, masking the HA token (never leak secrets)."""
    ha = cfg.ha.model_dump()
    ha["token"] = ""  # masked; a blank token on save means "leave unchanged"
    ha["has_token"] = bool(cfg.ha.token)
    return {
        "ha": ha,
        "site": cfg.site.model_dump(),
        "battery": cfg.battery.model_dump(),
        "reserve": cfg.reserve.model_dump(),
        "forecast": cfg.forecast.model_dump(),
        "control": cfg.control.model_dump(),
        "fail_safe": cfg.fail_safe.model_dump(),
        "engine": cfg.engine.model_dump(),
        "inverter": cfg.inverter.model_dump(),
        "load_shedding": cfg.load_shedding.model_dump(),
        "grid_charge": cfg.grid_charge.model_dump(),
    }


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
        }
    )


@router.get("/shed/snapshots")
async def shed_snapshots(
    request: Request,
    _admin: SessionUser = Depends(require_admin),
) -> dict:
    """Pending shed snapshots (debug / operator visibility)."""
    orch = _orch(request)
    snaps = orch.snapshot_store.list_all()
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


@router.get("/config")
async def get_config(
    request: Request,
    _admin: SessionUser = Depends(require_admin),
) -> dict:
    """Full (non-secret) effective config surfaced to the dashboard for editing."""
    return _config_view(_orch(request).cfg)


@router.get("/config/load-shedding")
async def get_load_shedding_config(
    request: Request,
    _session: SessionUser = Depends(require_authenticated),
) -> dict:
    """Read-only load shedding config for viewer dashboard tab."""
    cfg = _orch(request).cfg
    return {"load_shedding": cfg.load_shedding.model_dump()}


@router.put("/config")
async def put_config(
    request: Request,
    patch: dict = Body(...),
    _admin: SessionUser = Depends(require_admin),
) -> dict:
    """Apply a partial config update from the UI (deep-merged + persisted)."""
    orch = _orch(request)
    # Don't overwrite a stored HA token with the masked/blank value from the UI,
    # and ignore the read-only helper flag.
    ha_patch = patch.get("ha")
    if isinstance(ha_patch, dict):
        ha_patch.pop("has_token", None)
        if not ha_patch.get("token"):
            ha_patch.pop("token", None)
        if not ha_patch:
            patch.pop("ha", None)
    try:
        cfg = await orch.reload_config(patch)
    except ValidationError as e:
        raise HTTPException(
            status_code=422, detail=format_validation_errors(e.errors())
        ) from e
    except Exception as e:  # noqa: BLE001 - surface validation errors to the UI
        detail = str(e)
        if detail.startswith("api.config."):
            raise HTTPException(status_code=422, detail=t(detail)) from e
        raise HTTPException(status_code=422, detail=detail) from e
    return {"ok": True, "config": _config_view(cfg)}


@router.post("/config/reset")
async def reset_config(
    request: Request,
    _admin: SessionUser = Depends(require_admin),
) -> dict:
    cfg = await _orch(request).reset_config()
    return {"ok": True, "config": _config_view(cfg)}


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
    return localize_payload(await _orch(request).apply_override(ov))


@router.post("/override/clear")
async def clear_override(
    request: Request,
    _admin: SessionUser = Depends(require_admin),
) -> dict:
    orch = _orch(request)
    result = orch.clear_overrides()
    await orch.control_cycle()
    return localize_payload(result)


@router.get("/history/executions")
async def history_executions(
    request: Request, limit: int = Query(default=100, ge=1, le=1000)
) -> list[dict]:
    rows = await repo.get_recent_executions(limit=limit)
    return localize_payload(rows)  # type: ignore[return-value]


@router.get("/history/shed-executions")
async def history_shed_executions(
    request: Request, limit: int = Query(default=100, ge=1, le=1000)
) -> list[dict]:
    rows = await repo.get_recent_shed_executions(limit=limit)
    return localize_payload(rows)  # type: ignore[return-value]


class AssistRequest(BaseModel):
    question: str
    apply: bool = False


@router.post("/assistant/ask")
async def assistant_ask(
    request: Request,
    body: AssistRequest,
    _admin: SessionUser = Depends(require_admin),
) -> dict:
    """Natural-language Q&A and (optional) control via the local LLM assistant.

    The LLM only writes prose; control intents are parsed deterministically and
    applied only when `apply=true`.
    """
    orch = _orch(request)
    assistant = Assistant(orch.settings)

    status = orch.build_status()
    forecast = orch.forecast.current
    context = {
        "telemetry": status.telemetry.model_dump(mode="json") if status.telemetry else None,
        "decision": status.decision.model_dump(mode="json") if status.decision else None,
        "grid_stats": status.grid_stats.model_dump(mode="json") if status.grid_stats else None,
        "forecast": {
            "solar_today_kwh": forecast.solar_today_kwh if forecast else None,
            "solar_tomorrow_kwh": forecast.solar_tomorrow_kwh if forecast else None,
            "cloudy_tomorrow": forecast.cloudy_tomorrow if forecast else None,
        },
        "shadow_mode": orch.shadow_mode,
        "paused": orch.paused,
        "priority_order": [p.value for p in orch.cfg.engine.priority_order],
    }

    intent = assistant.parse_intent(body.question)
    answer = await assistant.answer(body.question, context)

    applied = None
    blocked = False
    block_reason: str | None = None
    if body.apply and intent is not None:
        if intent.kill_switch and not assistant.kill_switch_confirmed(body.question):
            answer = f"{answer}\n\n{t('api.override.assistant_kill_switch')}".strip()
            blocked = True
            block_reason = "kill_switch_confirm_required"
        else:
            applied = await orch.apply_override(intent)

    return _loc_data(
        {
            "answer": answer,
            "intent": intent.model_dump(mode="json") if intent else None,
            "applied": applied,
            "blocked": blocked,
            "block_reason": block_reason,
            "llm_enabled": assistant.enabled,
        }
    )
