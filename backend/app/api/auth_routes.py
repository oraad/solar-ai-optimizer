"""Local admin login/logout, auth status, and WebSocket ticket minting."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from ..config import get_settings
from ..i18n import api_error, t
from .login_rate_limit import (
    clear_login_failures,
    login_allowed,
    record_login_failure,
    retry_after_seconds,
)
from .session import (
    SESSION_COOKIE,
    SessionUser,
    _decode_cookie,
    clear_cookie_header_value,
    cookie_header_value,
    ensure_persisted_session_secret,
    make_session_cookie,
    require_authenticated,
    revoke_jti,
    verify_local_password,
)
from .ws_tickets import drop_tickets_for_jti, mint_ws_ticket

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.get("/status")
async def auth_status() -> dict:
    settings = get_settings()
    return {
        "local_auth_enabled": settings.local_auth_enabled,
        "login_required": settings.local_auth_enabled,
        "ingress_trusted": settings.ingress_trusted,
    }


@router.post("/login")
async def login(body: LoginRequest, request: Request, response: Response) -> dict:
    settings = get_settings()
    if not settings.local_auth_enabled:
        raise api_error("api.auth.local_login_disabled", 404)

    client_ip = _client_ip(request)
    if not login_allowed(client_ip):
        retry_after = retry_after_seconds(client_ip)
        raise HTTPException(
            status_code=429,
            detail=t("api.auth.rate_limited", {"retry_after": retry_after}),
            headers={"Retry-After": str(retry_after)},
        )

    valid = body.username == settings.local_admin_username and verify_local_password(
        body.password, settings
    )
    if not valid:
        record_login_failure(client_ip)
        raise api_error("api.auth.invalid_credentials", 401)

    clear_login_failures(client_ip)
    ensure_persisted_session_secret(settings)
    token = make_session_cookie(body.username, settings)
    response.headers["Set-Cookie"] = cookie_header_value(token, settings)
    return {"ok": True}


@router.post("/logout")
async def logout(request: Request, response: Response) -> dict:
    settings = get_settings()
    raw = request.cookies.get(SESSION_COOKIE)
    if raw:
        payload = _decode_cookie(raw, settings)
        if payload:
            jti = payload.get("jti")
            exp = payload.get("exp")
            if isinstance(jti, str) and isinstance(exp, (int, float)):
                revoke_jti(jti, float(exp))
                drop_tickets_for_jti(jti)
    response.headers["Set-Cookie"] = clear_cookie_header_value(settings)
    return {"ok": True}


@router.post("/ws-ticket")
async def ws_ticket(
    request: Request,
    session: SessionUser = Depends(require_authenticated),
) -> dict:
    """Mint a short-lived, single-use ticket for the /ws upgrade (?ticket=).

    When the caller is a local-cookie session, the ticket is tied to that
    cookie's jti so logout (which revokes the jti) also invalidates any
    outstanding tickets minted for it.
    """
    settings = get_settings()
    jti: str | None = None
    if session.auth_mode == "local":
        raw = request.cookies.get(SESSION_COOKIE)
        if raw:
            payload = _decode_cookie(raw, settings)
            if payload:
                candidate = payload.get("jti")
                if isinstance(candidate, str):
                    jti = candidate
    return mint_ws_ticket(session, settings, jti=jti)
