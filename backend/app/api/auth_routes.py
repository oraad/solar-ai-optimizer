"""Local admin login/logout and auth status."""

from __future__ import annotations

from fastapi import APIRouter, Response
from pydantic import BaseModel

from ..config import get_settings
from ..i18n import api_error
from .session import (
    clear_cookie_header_value,
    cookie_header_value,
    make_session_cookie,
    verify_local_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


@router.get("/status")
async def auth_status() -> dict:
    settings = get_settings()
    return {
        "local_auth_enabled": settings.local_auth_enabled,
        "login_required": settings.local_auth_enabled,
        "ingress_trusted": settings.ingress_trusted,
    }


@router.post("/login")
async def login(body: LoginRequest, response: Response) -> dict:
    settings = get_settings()
    if not settings.local_auth_enabled:
        raise api_error("api.auth.local_login_disabled", 404)

    if body.username != settings.local_admin_username:
        raise api_error("api.auth.invalid_credentials", 401)
    if not verify_local_password(body.password, settings):
        raise api_error("api.auth.invalid_credentials", 401)

    token = make_session_cookie(body.username, settings)
    response.headers["Set-Cookie"] = cookie_header_value(token, settings)
    return {"ok": True}


@router.post("/logout")
async def logout(response: Response) -> dict:
    response.headers["Set-Cookie"] = clear_cookie_header_value()
    return {"ok": True}
