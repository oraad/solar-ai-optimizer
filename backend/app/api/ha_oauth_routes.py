"""Solar → Home Assistant IndieAuth endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from ..config import Settings, get_settings
from ..ha import oauth as ha_oauth
from ..i18n import api_error
from .session import SessionUser, require_admin

router = APIRouter(prefix="/api/ha/oauth", tags=["ha-oauth"])


class StartBody(BaseModel):
    public_base_url: str = Field(min_length=8, max_length=512)
    ha_base_url: str | None = Field(default=None, max_length=512)


@router.get("/status")
async def oauth_status(
    _admin: SessionUser = Depends(require_admin),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    return ha_oauth.oauth_status(settings.data_dir)


@router.post("/start")
async def oauth_start(
    body: StartBody,
    _admin: SessionUser = Depends(require_admin),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    if settings.is_addon:
        raise api_error("api.ha_oauth.addon_unsupported", 400)
    ha_url = (body.ha_base_url or settings.ha_base_url).strip()
    try:
        started = ha_oauth.start_authorize(
            settings.data_dir,
            ha_base_url=ha_url,
            public_base_url=body.public_base_url,
        )
    except ValueError as exc:
        raise api_error("api.ha_oauth.invalid_url", 400) from exc
    return {
        "authorize_url": started.authorize_url,
        "state": started.state,
        "expires_at": started.expires_at,
    }


@router.get("/callback")
async def oauth_callback(
    code: str = Query(...),
    state: str = Query(...),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    try:
        await ha_oauth.finish_authorize(
            settings.data_dir,
            code=code,
            state=state,
            verify_ssl=settings.ha_verify_ssl,
        )
        msg = "Home Assistant connected. You can close this window."
        ok = True
    except ha_oauth.OAuthError as exc:
        msg = f"Connection failed ({exc.code}). Close this window and try again."
        ok = False
    color = "#0a7" if ok else "#c33"
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>Solar AI</title></head>
<body style="font-family:system-ui;padding:2rem;text-align:center">
<h1 style="color:{color}">{"Connected" if ok else "Failed"}</h1>
<p>{msg}</p>
</body></html>"""
    return HTMLResponse(html, status_code=200 if ok else 400)


@router.delete("/disconnect")
async def oauth_disconnect(
    _admin: SessionUser = Depends(require_admin),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    ha_oauth.clear_oauth(settings.data_dir)
    return {"ok": True}
