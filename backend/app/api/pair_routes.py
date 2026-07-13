"""One-time pairing codes for HA / machine clients."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from ..auth.api_clients import (
    PairingError,
    cancel_pairing,
    list_clients,
    pending_status,
    redeem_pairing,
    revoke_client,
    start_pairing,
)
from ..auth.install_id import get_or_create_install_id
from ..config import Settings, get_settings
from ..i18n import api_error
from .session import SessionUser, require_admin

router = APIRouter(prefix="/api/pair", tags=["pair"])


class RedeemBody(BaseModel):
    code: str = Field(min_length=4, max_length=32)
    client_name: str = Field(default="Home Assistant", max_length=128)
    client_version: str | None = Field(default=None, max_length=64)
    integration: str | None = Field(default=None, max_length=64)


@router.post("/start")
async def pair_start(
    _admin: SessionUser = Depends(require_admin),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    try:
        return await asyncio.to_thread(
            start_pairing,
            settings.data_dir,
            created_by=_admin.user_id or _admin.username,
        )
    except PairingError as exc:
        if exc.code == "rate_limited":
            raise api_error("api.pair.rate_limited", 429) from exc
        raise api_error("api.pair.failed", 400) from exc


@router.get("/status")
async def pair_status(
    _admin: SessionUser = Depends(require_admin),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    pending, clients, install_id = await asyncio.gather(
        asyncio.to_thread(pending_status, settings.data_dir),
        asyncio.to_thread(list_clients, settings.data_dir),
        asyncio.to_thread(get_or_create_install_id, settings.data_dir),
    )
    return {"pending": pending, "clients": clients, "install_id": install_id}


@router.post("/cancel")
async def pair_cancel(
    _admin: SessionUser = Depends(require_admin),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    await asyncio.to_thread(cancel_pairing, settings.data_dir)
    return {"ok": True}


@router.post("/redeem", status_code=201)
async def pair_redeem(
    body: RedeemBody,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    client_ip = request.client.host if request.client else ""
    try:
        minted = await asyncio.to_thread(
            redeem_pairing,
            settings.data_dir,
            code=body.code,
            client_name=body.client_name,
            client_ip=client_ip,
        )
    except PairingError as exc:
        if exc.code == "rate_limited":
            raise api_error("api.pair.rate_limited", 429) from exc
        if exc.status == 409:
            raise api_error("api.pair.conflict", 409) from exc
        raise api_error("api.pair.invalid_or_expired", 400) from exc
    minted["install_id"] = await asyncio.to_thread(
        get_or_create_install_id, settings.data_dir
    )
    from .. import __version__

    minted["solar_version"] = __version__
    return minted


@router.delete("/clients/{client_id}", status_code=204)
async def pair_revoke(
    client_id: str,
    _admin: SessionUser = Depends(require_admin),
    settings: Settings = Depends(get_settings),
) -> None:
    revoked = await asyncio.to_thread(revoke_client, settings.data_dir, client_id)
    if not revoked:
        raise api_error("api.pair.client_not_found", 404)
