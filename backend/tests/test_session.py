"""Session resolution, cookies, and ingress bypass."""

from __future__ import annotations

from unittest.mock import AsyncMock

import bcrypt
import pytest
from starlette.requests import Request

from app.api.session import (
    ANONYMOUS,
    INGRESS_USER_ID,
    ingress_headers_allowed,
    make_session_cookie,
    open_session,
    parse_ingress_headers,
    resolve_session,
    verify_local_password,
)
from app.config import Settings


def _settings(**kwargs) -> Settings:
    return Settings(
        ha_token="",
        database_url="sqlite+aiosqlite:///:memory:",
        **kwargs,
    )


def _request(headers: dict | None = None, cookies: dict | None = None) -> Request:
    hdrs = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    if cookies:
        cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())
        hdrs.append((b"cookie", cookie_str.encode()))
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/status",
        "headers": hdrs,
        "query_string": b"",
        "client": ("127.0.0.1", 1234),
        "server": ("test", 80),
        "scheme": "http",
        "root_path": "",
    }
    return Request(scope)


def test_parse_ingress_headers():
    req = _request({INGRESS_USER_ID: "user-1", "X-Remote-User-Name": "omar"})
    assert parse_ingress_headers(req) == ("user-1", "omar", None)


@pytest.mark.asyncio
async def test_ingress_takes_priority_over_bearer():
    settings = _settings(
        trust_ingress_headers=True,
        trusted_proxy_ips="127.0.0.1",
        api_token="secret",
        local_admin_password="adminpass",
        session_secret="test-secret",
    )
    resolver = AsyncMock()
    resolver.is_admin = AsyncMock(return_value=False)
    req = _request(
        {
            INGRESS_USER_ID: "ha-user",
            "Authorization": "Bearer secret",
        },
    )
    session = await resolve_session(req, settings, resolver)
    assert session.auth_mode == "ingress"
    assert session.user_id == "ha-user"
    assert session.is_admin is False


@pytest.mark.asyncio
async def test_bearer_token_admin():
    settings = _settings(api_token="secret")
    req = _request({"Authorization": "Bearer secret"})
    session = await resolve_session(req, settings, None)
    assert session.auth_mode == "token"
    assert session.is_admin is True


@pytest.mark.asyncio
async def test_local_cookie_session():
    password_hash = bcrypt.hashpw(b"pass", bcrypt.gensalt()).decode()
    settings = _settings(
        local_admin_username="admin",
        local_admin_password_hash=password_hash,
        session_secret="cookie-secret",
    )
    token = make_session_cookie("admin", settings)
    req = _request(cookies={"solar_session": token})
    session = await resolve_session(req, settings, None)
    assert session.auth_mode == "local"
    assert session.is_admin is True


def test_verify_local_password_hash():
    password_hash = bcrypt.hashpw(b"secret", bcrypt.gensalt()).decode()
    settings = _settings(local_admin_password_hash=password_hash)
    assert verify_local_password("secret", settings)
    assert not verify_local_password("wrong", settings)


@pytest.mark.asyncio
async def test_admin_allowlist():
    settings = _settings(
        trust_ingress_headers=True,
        trusted_proxy_ips="127.0.0.1",
        admin_user_ids="user-1,user-2",
    )
    req = _request({INGRESS_USER_ID: "user-1"})
    session = await resolve_session(req, settings, None)
    assert session.is_admin is True


@pytest.mark.asyncio
async def test_open_session_denied_when_ingress_trusted_without_headers():
    settings = _settings(trust_ingress_headers=True)
    req = _request()
    session = await resolve_session(req, settings, None)
    assert session is ANONYMOUS
    assert session.authenticated is False


@pytest.mark.asyncio
async def test_open_session_still_admin_when_ingress_untrusted():
    settings = _settings(trust_ingress_headers=False, allow_open_access=True)
    session = await open_session(settings)
    assert session is not None
    assert session.auth_mode == "open"
    assert session.is_admin is True


@pytest.mark.asyncio
async def test_open_session_denied_without_allow_open_access():
    settings = _settings(trust_ingress_headers=False, allow_open_access=False)
    assert await open_session(settings) is None


@pytest.mark.asyncio
async def test_mcp_token_bearer_not_rest_admin():
    settings = _settings(mcp_token="mcp-only", api_token="")
    req = _request({"Authorization": "Bearer mcp-only"})
    session = await resolve_session(req, settings, None)
    assert session.auth_mode == "mcp"
    assert session.is_admin is False
    assert session.authenticated is True


@pytest.mark.asyncio
async def test_ingress_requires_trusted_proxy_outside_addon():
    settings = _settings(
        trust_ingress_headers=True,
        trusted_proxy_ips="10.0.0.1",
        admin_user_ids="user-1",
    )
    # Client IP in _request is 127.0.0.1 — not trusted.
    req = _request({INGRESS_USER_ID: "user-1"})
    session = await resolve_session(req, settings, None)
    assert session.auth_mode != "ingress"


@pytest.mark.asyncio
async def test_ingress_allowed_from_trusted_proxy():
    settings = _settings(
        trust_ingress_headers=True,
        trusted_proxy_ips="127.0.0.1",
        admin_user_ids="user-1",
    )
    req = _request({INGRESS_USER_ID: "user-1"})
    session = await resolve_session(req, settings, None)
    assert session.auth_mode == "ingress"
    assert session.is_admin is True


def test_ingress_headers_denied_when_no_trusted_proxies_configured():
    """Fail closed outside the add-on when TRUSTED_PROXY_IPS is unset."""
    settings = _settings(trust_ingress_headers=True)
    req = _request({INGRESS_USER_ID: "user-1"})
    assert ingress_headers_allowed(req, settings) is False


def test_ingress_headers_allowed_when_addon_even_without_trusted_proxies():
    """The HA Supervisor add-on network is always trusted."""
    settings = _settings(**{"SUPERVISOR_TOKEN": "supervisor-secret"})
    assert settings.is_addon is True
    req = _request({INGRESS_USER_ID: "user-1"})
    assert ingress_headers_allowed(req, settings) is True


@pytest.mark.asyncio
async def test_supervisor_token_bearer_admin_when_addon():
    settings = _settings(**{"SUPERVISOR_TOKEN": "supervisor-secret"})
    assert settings.is_addon is True
    req = _request({"Authorization": "Bearer supervisor-secret"})
    session = await resolve_session(req, settings, None)
    assert session.auth_mode == "supervisor"
    assert session.is_admin is True
    assert session.user_id == "supervisor"


@pytest.mark.asyncio
async def test_supervisor_token_ignored_when_not_addon():
    settings = _settings(api_token="", allow_open_access=False)
    # No SUPERVISOR_TOKEN → is_addon false; matching a random bearer fails.
    req = _request({"Authorization": "Bearer supervisor-secret"})
    session = await resolve_session(req, settings, None)
    assert session is ANONYMOUS
    assert session.authenticated is False


@pytest.mark.asyncio
async def test_supervisor_token_preferred_over_api_token_when_same():
    """When both match the same secret, addon path reports supervisor mode."""
    secret = "shared-secret"
    settings = _settings(api_token=secret, **{"SUPERVISOR_TOKEN": secret})
    req = _request({"Authorization": f"Bearer {secret}"})
    session = await resolve_session(req, settings, None)
    assert session.auth_mode == "supervisor"
