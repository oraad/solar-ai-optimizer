"""Repository: typed read/write helpers over the ORM tables."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Literal

from sqlalchemy import delete, select

from ..i18n.serialize import decode_msg, encode_msg
from ..models import (
    Decision,
    ExecutionResult,
    GridEvent,
    Msg,
    ShedResult,
    Telemetry,
    as_utc,
    utcnow,
)
from .db import get_sessionmaker
from .orm import (
    DecisionRow,
    ExecutionRow,
    GridEventRow,
    ShedExecutionRow,
    TelemetryRow,
)


async def save_telemetry(t: Telemetry) -> None:
    sm = get_sessionmaker()
    async with sm() as s:
        s.add(
            TelemetryRow(
                ts=t.ts,
                pv_power=t.pv_power,
                load_power=t.load_power,
                battery_soc=t.battery_soc,
                battery_power=t.battery_power,
                grid_power=t.grid_power,
                grid_present=t.grid_present,
                battery_temp=t.battery_temp,
                outdoor_temp=t.outdoor_temp,
            )
        )
        await s.commit()


async def get_telemetry_since(since: datetime) -> list[Telemetry]:
    sm = get_sessionmaker()
    async with sm() as s:
        rows = (
            await s.execute(
                select(TelemetryRow)
                .where(TelemetryRow.ts >= since)
                .order_by(TelemetryRow.ts.asc())
            )
        ).scalars().all()
    return [
        Telemetry(
            ts=as_utc(r.ts),
            pv_power=r.pv_power,
            load_power=r.load_power,
            battery_soc=r.battery_soc,
            battery_power=r.battery_power,
            grid_power=r.grid_power,
            grid_present=r.grid_present,
            battery_temp=r.battery_temp,
            outdoor_temp=r.outdoor_temp,
        )
        for r in rows
    ]


async def get_recent_telemetry(limit: int = 500) -> list[Telemetry]:
    sm = get_sessionmaker()
    async with sm() as s:
        rows = (
            await s.execute(
                select(TelemetryRow).order_by(TelemetryRow.ts.desc()).limit(limit)
            )
        ).scalars().all()
    rows = list(reversed(rows))
    return [
        Telemetry(
            ts=as_utc(r.ts),
            pv_power=r.pv_power,
            load_power=r.load_power,
            battery_soc=r.battery_soc,
            battery_power=r.battery_power,
            grid_power=r.grid_power,
            grid_present=r.grid_present,
            battery_temp=r.battery_temp,
            outdoor_temp=r.outdoor_temp,
        )
        for r in rows
    ]


async def save_grid_event(ev: GridEvent) -> None:
    sm = get_sessionmaker()
    async with sm() as s:
        s.add(GridEventRow(ts=ev.ts, grid_present=ev.grid_present))
        await s.commit()


async def get_grid_events_since(
    since: datetime, *, order: Literal["asc", "desc"] = "asc"
) -> list[GridEvent]:
    sm = get_sessionmaker()
    async with sm() as s:
        rows = (
            await s.execute(
                select(GridEventRow)
                .where(GridEventRow.ts >= since)
                .order_by(
                    GridEventRow.ts.asc()
                    if order == "asc"
                    else GridEventRow.ts.desc()
                )
            )
        ).scalars().all()
    return [GridEvent(ts=as_utc(r.ts), grid_present=r.grid_present) for r in rows]


async def get_last_grid_event() -> GridEvent | None:
    sm = get_sessionmaker()
    async with sm() as s:
        row = (
            await s.execute(
                select(GridEventRow).order_by(GridEventRow.ts.desc()).limit(1)
            )
        ).scalar_one_or_none()
    if row is None:
        return None
    return GridEvent(ts=as_utc(row.ts), grid_present=row.grid_present)


def _decision_row_fields(d: Decision) -> dict[str, str | float | bool]:
    """Audit payload persisted to decisions (excludes ts and cycle_id)."""
    grid_charge_json = ""
    if d.grid_charge is not None:
        grid_charge_json = json.dumps(d.grid_charge.model_dump(mode="json"))
    explanation_json = ""
    if d.explanation is not None:
        explanation_json = json.dumps(d.explanation.model_dump(mode="json"))
    return {
        "target_soc": round(d.reserve.target_soc, 1),
        "blackout_risk": d.blackout_risk.value,
        "blackout_risk_score": round(d.blackout_risk_score, 3),
        "shadow_mode": d.shadow_mode,
        "summary": (
            encode_msg(d.summary) if isinstance(d.summary, Msg) else str(d.summary)
        ),
        "reserve_rationale": encode_msg(d.reserve.rationale),
        "actions_json": json.dumps([a.model_dump(mode="json") for a in d.actions]),
        "shed_actions_json": json.dumps(
            [a.model_dump(mode="json") for a in d.shed_actions]
        ),
        "grid_charge_json": grid_charge_json,
        "explanation_json": explanation_json,
        "engine_active": (
            d.explanation.modifiers.engine_active
            if d.explanation is not None
            else "rules"
        ),
    }


def decisions_audit_equal(prev: Decision | None, cur: Decision) -> bool:
    if prev is None:
        return False
    return _decision_row_fields(prev) == _decision_row_fields(cur)


async def save_decision(d: Decision, *, slim: bool = False) -> None:
    """Persist a decision row. slim=True stores header fields only (no body JSON)."""
    sm = get_sessionmaker()
    fields = _decision_row_fields(d)
    if slim:
        actions_json = "[]"
        shed_actions_json = "[]"
        grid_charge_json = ""
        explanation_json = ""
    else:
        actions_json = fields["actions_json"]  # type: ignore[assignment]
        shed_actions_json = fields["shed_actions_json"]  # type: ignore[assignment]
        grid_charge_json = fields["grid_charge_json"]  # type: ignore[assignment]
        explanation_json = fields["explanation_json"]  # type: ignore[assignment]
    async with sm() as s:
        s.add(
            DecisionRow(
                ts=d.ts,
                cycle_id=d.cycle_id,
                target_soc=fields["target_soc"],  # type: ignore[arg-type]
                blackout_risk=fields["blackout_risk"],  # type: ignore[arg-type]
                blackout_risk_score=fields["blackout_risk_score"],  # type: ignore[arg-type]
                shadow_mode=fields["shadow_mode"],  # type: ignore[arg-type]
                summary=fields["summary"],  # type: ignore[arg-type]
                reserve_rationale=fields["reserve_rationale"],  # type: ignore[arg-type]
                actions_json=actions_json,
                shed_actions_json=shed_actions_json,
                grid_charge_json=grid_charge_json,
                explanation_json=explanation_json,
                engine_active=fields["engine_active"],  # type: ignore[arg-type]
                slim=slim,
            )
        )
        await s.commit()


def _parse_json_obj(raw: str | None, default: object) -> object:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default


async def get_recent_decisions(limit: int = 100) -> list[dict]:
    sm = get_sessionmaker()
    async with sm() as s:
        rows = (
            await s.execute(
                select(DecisionRow).order_by(DecisionRow.ts.desc()).limit(limit)
            )
        ).scalars().all()
    return [_decision_row_to_dict(r) for r in rows]


async def get_decisions_by_cycle_id(cycle_id: str, limit: int = 20) -> list[dict]:
    sm = get_sessionmaker()
    async with sm() as s:
        rows = (
            await s.execute(
                select(DecisionRow)
                .where(DecisionRow.cycle_id == cycle_id)
                .order_by(DecisionRow.ts.desc())
                .limit(limit)
            )
        ).scalars().all()
    return [_decision_row_to_dict(r) for r in rows]


def _decision_row_to_dict(r: DecisionRow) -> dict:
    return {
        "ts": r.ts.isoformat(),
        "cycle_id": getattr(r, "cycle_id", None),
        "target_soc": r.target_soc,
        "blackout_risk": r.blackout_risk,
        "blackout_risk_score": r.blackout_risk_score,
        "shadow_mode": r.shadow_mode,
        "summary": r.summary,
        "reserve_rationale": getattr(r, "reserve_rationale", "") or "",
        "actions": _parse_json_obj(r.actions_json, []),
        "shed_actions": _parse_json_obj(
            getattr(r, "shed_actions_json", None) or "[]", []
        ),
        "grid_charge": _parse_json_obj(
            getattr(r, "grid_charge_json", None) or "", None
        ),
        "explanation": _parse_json_obj(
            getattr(r, "explanation_json", None) or "", None
        ),
        "engine_active": getattr(r, "engine_active", None) or "rules",
        "slim": bool(getattr(r, "slim", False)),
    }


def _execution_audit_fields(e: ExecutionResult) -> dict:
    """Audit payload persisted to executions (excludes ts and cycle_id)."""
    return {
        "capability": e.capability.value,
        "requested": str(e.requested),
        "applied": e.applied,
        "verified": e.verified,
        "skipped_reason": e.skipped_reason,
        "error": e.error,
    }


def executions_audit_equal(prev: ExecutionResult | None, cur: ExecutionResult) -> bool:
    if prev is None:
        return False
    return _execution_audit_fields(prev) == _execution_audit_fields(cur)


def _shed_execution_audit_fields(r: ShedResult) -> dict:
    """Audit payload persisted to shed_executions (excludes ts and cycle_id)."""
    return {
        "tier": r.tier,
        "entity": r.entity,
        "desired_on": r.desired_on,
        "applied": r.applied,
        "verified": r.verified,
        "skipped_reason": r.skipped_reason,
        "error": r.error,
        "companions_captured": list(r.companions_captured),
        "companions_restored": list(r.companions_restored),
        "companion_errors": dict(r.companion_errors),
    }


def shed_executions_audit_equal(prev: ShedResult | None, cur: ShedResult) -> bool:
    if prev is None:
        return False
    return _shed_execution_audit_fields(prev) == _shed_execution_audit_fields(cur)


async def save_execution(e: ExecutionResult) -> None:
    sm = get_sessionmaker()
    async with sm() as s:
        s.add(
            ExecutionRow(
                ts=e.ts,
                cycle_id=e.cycle_id,
                capability=e.capability.value,
                requested=str(e.requested),
                applied=e.applied,
                verified=e.verified,
                skipped_reason=e.skipped_reason,
                error=e.error,
            )
        )
        await s.commit()


async def get_recent_executions(
    limit: int = 100, *, cycle_id: str | None = None
) -> list[dict]:
    sm = get_sessionmaker()
    async with sm() as s:
        stmt = select(ExecutionRow).order_by(ExecutionRow.ts.desc()).limit(limit)
        if cycle_id:
            stmt = (
                select(ExecutionRow)
                .where(ExecutionRow.cycle_id == cycle_id)
                .order_by(ExecutionRow.ts.desc())
                .limit(limit)
            )
        rows = (await s.execute(stmt)).scalars().all()
    return [
        {
            "ts": r.ts.isoformat(),
            "cycle_id": getattr(r, "cycle_id", None),
            "capability": r.capability,
            "requested": r.requested,
            "applied": r.applied,
            "verified": r.verified,
            "skipped_reason": r.skipped_reason,
            "error": r.error,
        }
        for r in rows
    ]


async def save_shed_execution(r: ShedResult) -> None:
    audit = {
        "companions_captured": r.companions_captured,
        "companions_restored": r.companions_restored,
        "companion_errors": r.companion_errors,
    }
    sm = get_sessionmaker()
    async with sm() as s:
        s.add(
            ShedExecutionRow(
                ts=r.ts,
                cycle_id=r.cycle_id,
                tier=r.tier,
                entity=r.entity,
                desired_on=r.desired_on,
                applied=r.applied,
                verified=r.verified,
                skipped_reason=r.skipped_reason,
                error=r.error,
                companion_audit_json=json.dumps(audit),
            )
        )
        await s.commit()


async def get_recent_shed_executions(
    limit: int = 100, *, cycle_id: str | None = None
) -> list[dict]:
    sm = get_sessionmaker()
    async with sm() as s:
        stmt = (
            select(ShedExecutionRow)
            .order_by(ShedExecutionRow.ts.desc())
            .limit(limit)
        )
        if cycle_id:
            stmt = (
                select(ShedExecutionRow)
                .where(ShedExecutionRow.cycle_id == cycle_id)
                .order_by(ShedExecutionRow.ts.desc())
                .limit(limit)
            )
        rows = (await s.execute(stmt)).scalars().all()
    out: list[dict] = []
    for r in rows:
        audit_raw = getattr(r, "companion_audit_json", None) or "{}"
        try:
            audit = json.loads(audit_raw)
        except json.JSONDecodeError:
            audit = {}
        out.append(
            {
                "ts": r.ts.isoformat(),
                "cycle_id": getattr(r, "cycle_id", None),
                "tier": r.tier,
                "entity": r.entity,
                "desired_on": r.desired_on,
                "applied": r.applied,
                "verified": r.verified,
                "skipped_reason": r.skipped_reason,
                "error": r.error,
                "companions_captured": audit.get("companions_captured", []),
                "companions_restored": audit.get("companions_restored", []),
                "companion_errors": audit.get("companion_errors", {}),
            }
        )
    return out


async def purge_older_than(days: int) -> int:
    """Delete rows older than N days across all time-series tables."""
    cutoff = utcnow() - timedelta(days=days)
    sm = get_sessionmaker()
    total = 0
    async with sm() as s:
        for table in (
            TelemetryRow,
            GridEventRow,
            DecisionRow,
            ExecutionRow,
            ShedExecutionRow,
        ):
            result = await s.execute(delete(table).where(table.ts < cutoff))
            total += result.rowcount or 0
        await s.commit()
    return total
