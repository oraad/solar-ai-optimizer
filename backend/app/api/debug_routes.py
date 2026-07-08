"""Admin debug endpoints for decision forensics."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query, Request

from ..i18n import t
from ..i18n.serialize import localize_payload
from ..mcp.rate_limit import rate_limiter
from ..services import SolarOps
from .session import SessionUser, require_admin
from .timezone import site_tz_for

log = logging.getLogger("api.debug")

router = APIRouter(prefix="/api/debug", tags=["debug"])


def _ops(request: Request) -> SolarOps:
    return SolarOps(request.app.state.orchestrator)


def _rate_key(request: Request) -> str:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:].strip()[:32] or "anonymous"
    return request.client.host if request.client else "anonymous"


@router.get("/trace")
async def debug_trace(
    request: Request,
    sections: str | None = Query(default=None),
    _admin: SessionUser = Depends(require_admin),
) -> dict:
    """Read-only decision forensics bundle (admin)."""
    ops = _ops(request)
    log.info("debug_trace sections=%s", sections or "default")
    data = ops.decision_trace(sections=sections)
    return localize_payload(data, site_tz=site_tz_for(ops.orch))


@router.post("/simulate")
async def debug_simulate(
    request: Request,
    _admin: SessionUser = Depends(require_admin),
) -> dict:
    """Dry-run decision without applying writes (admin, rate-limited)."""
    key = _rate_key(request)
    if not rate_limiter.allow(key, "simulate"):
        from fastapi import HTTPException

        raise HTTPException(status_code=429, detail=t("api.debug.rate_limit"))
    ops = _ops(request)
    log.info("debug_simulate")
    data = ops.simulate_decision()
    return localize_payload(data, site_tz=site_tz_for(ops.orch))
