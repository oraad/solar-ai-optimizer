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
    """Audit payload persisted to decisions (excludes ts)."""
    return {
        "target_soc": d.reserve.target_soc,
        "blackout_risk": d.blackout_risk.value,
        "blackout_risk_score": d.blackout_risk_score,
        "shadow_mode": d.shadow_mode,
        "summary": (
            encode_msg(d.summary) if isinstance(d.summary, Msg) else str(d.summary)
        ),
        "reserve_rationale": encode_msg(d.reserve.rationale),
        "actions_json": json.dumps([a.model_dump(mode="json") for a in d.actions]),
        "shed_actions_json": json.dumps(
            [a.model_dump(mode="json") for a in d.shed_actions]
        ),
    }


def decisions_audit_equal(prev: Decision | None, cur: Decision) -> bool:
    if prev is None:
        return False
    return _decision_row_fields(prev) == _decision_row_fields(cur)


async def save_decision(d: Decision) -> None:
    sm = get_sessionmaker()
    fields = _decision_row_fields(d)
    async with sm() as s:
        s.add(
            DecisionRow(
                ts=d.ts,
                target_soc=fields["target_soc"],  # type: ignore[arg-type]
                blackout_risk=fields["blackout_risk"],  # type: ignore[arg-type]
                blackout_risk_score=fields["blackout_risk_score"],  # type: ignore[arg-type]
                shadow_mode=fields["shadow_mode"],  # type: ignore[arg-type]
                summary=fields["summary"],  # type: ignore[arg-type]
                reserve_rationale=fields["reserve_rationale"],  # type: ignore[arg-type]
                actions_json=fields["actions_json"],  # type: ignore[arg-type]
                shed_actions_json=fields["shed_actions_json"],  # type: ignore[arg-type]
            )
        )
        await s.commit()


async def get_recent_decisions(limit: int = 100) -> list[dict]:
    sm = get_sessionmaker()
    async with sm() as s:
        rows = (
            await s.execute(
                select(DecisionRow).order_by(DecisionRow.ts.desc()).limit(limit)
            )
        ).scalars().all()
    return [
        {
            "ts": r.ts.isoformat(),
            "target_soc": r.target_soc,
            "blackout_risk": r.blackout_risk,
            "blackout_risk_score": r.blackout_risk_score,
            "shadow_mode": r.shadow_mode,
            "summary": r.summary,
            "reserve_rationale": getattr(r, "reserve_rationale", "") or "",
            "actions": json.loads(r.actions_json or "[]"),
            "shed_actions": json.loads(getattr(r, "shed_actions_json", None) or "[]"),
        }
        for r in rows
    ]


def _execution_audit_fields(e: ExecutionResult) -> dict:
    """Audit payload persisted to executions (excludes ts)."""
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
    """Audit payload persisted to shed_executions (excludes ts)."""
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
                capability=e.capability.value,
                requested=str(e.requested),
                applied=e.applied,
                verified=e.verified,
                skipped_reason=e.skipped_reason,
                error=e.error,
            )
        )
        await s.commit()


async def get_recent_executions(limit: int = 100) -> list[dict]:
    sm = get_sessionmaker()
    async with sm() as s:
        rows = (
            await s.execute(
                select(ExecutionRow).order_by(ExecutionRow.ts.desc()).limit(limit)
            )
        ).scalars().all()
    return [
        {
            "ts": r.ts.isoformat(),
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
    import json

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


async def get_recent_shed_executions(limit: int = 100) -> list[dict]:
    import json

    sm = get_sessionmaker()
    async with sm() as s:
        rows = (
            await s.execute(
                select(ShedExecutionRow)
                .order_by(ShedExecutionRow.ts.desc())
                .limit(limit)
            )
        ).scalars().all()
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
