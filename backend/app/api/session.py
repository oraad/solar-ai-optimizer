"""Session identity: HA ingress headers, local cookie, bearer token, or open dev mode."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import ipaddress
import json
import logging
import re
import secrets
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import bcrypt
from fastapi import HTTPException, Request
from starlette.requests import HTTPConnection

from ..i18n import api_error

from .. import __version__
from ..config import Settings, get_settings
from ..models import Override

log = logging.getLogger("api.session")

AuthMode = Literal[
    "ingress", "local", "token", "client", "supervisor", "mcp", "open", "none"
]

SESSION_COOKIE = "solar_session"

INGRESS_USER_ID = "X-Remote-User-Id"
INGRESS_USER_NAME = "X-Remote-User-Name"
INGRESS_DISPLAY_NAME = "X-Remote-User-Display-Name"

# Exact-path match via is_public_api_path(); not a prefix.
PUBLIC_API_PREFIXES = (
    "/api/health",
    "/api/ping",
    "/api/auth/login",
    "/api/auth/logout",
    "/api/auth/status",
    "/api/pair/redeem",
    "/api/ha/oauth/callback",
)

# Gated like /api/* when credentials are configured, but not "public API" routes.
_DOC_PATHS = ("/docs", "/openapi.json", "/redoc")

_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")


@dataclass(frozen=True)
class SessionUser:
    user_id: str | None
    username: str | None
    display_name: str | None
    is_admin: bool
    auth_mode: AuthMode

    @property
    def authenticated(self) -> bool:
        return self.auth_mode != "none"

    def to_me_dict(self, settings: Settings) -> dict[str, Any]:
        login_required = settings.local_auth_enabled and not settings.ingress_trusted
        return {
            "authenticated": self.authenticated,
            "auth_mode": self.auth_mode,
            "user_id": self.user_id,
            "username": self.username,
            "display_name": self.display_name,
            "is_admin": self.is_admin,
            "login_required": login_required,
            "version": __version__,
            "is_addon": settings.is_addon,
        }


ANONYMOUS = SessionUser(
    user_id=None,
    username=None,
    display_name=None,
    is_admin=False,
    auth_mode="none",
)


def sanitize_request_id(raw: str | None) -> str:
    """Validate an inbound X-Request-ID; fall back to a fresh UUID4 if unsafe.

    Client-supplied request IDs are echoed back and logged, so they must be
    constrained to a safe charset/length to avoid header/log injection.
    """
    if raw and _REQUEST_ID_RE.match(raw):
        return raw
    return str(uuid.uuid4())


def ensure_persisted_session_secret(settings: Settings) -> str:
    """Ensure a durable SESSION_SECRET exists on disk; generate one if missing.

    Without this, an unset SESSION_SECRET falls back to an ephemeral,
    process-local key (see `_session_secret`), invalidating all sessions on
    every restart. Local admin logins persist the secret to
    `<data_dir>/local_auth.env` (same file used by reset-local-password) so
    cookies remain valid across restarts. Never overwrites an existing
    on-disk secret or an existing password hash.
    """
    if settings.session_secret.strip():
        return settings.session_secret

    from ..auth.local_credentials import (
        generate_session_secret,
        local_auth_env_path,
        read_env_value,
        write_local_auth_env,
    )

    path = local_auth_env_path(Path(settings.data_dir))
    existing = read_env_value(path, "SESSION_SECRET")
    if existing:
        settings.session_secret = existing
        return existing

    secret = generate_session_secret()
    username = read_env_value(path, "LOCAL_ADMIN_USERNAME") or settings.local_admin_username
    password_hash = (
        read_env_value(path, "LOCAL_ADMIN_PASSWORD_HASH")
        or settings.local_admin_password_hash
    )
    write_local_auth_env(
        path,
        username=username,
        password_hash=password_hash,
        session_secret=secret,
    )
    settings.session_secret = secret
    return secret


def _session_secret(settings: Settings) -> bytes:
    raw = settings.session_secret.strip()
    if raw:
        return raw.encode("utf-8")
    if settings.local_auth_enabled:
        log.warning(
            "SESSION_SECRET is not set — using ephemeral secret; "
            "sessions reset on restart."
        )
    return hashlib.sha256(
        f"ephemeral-{settings.data_dir}".encode("utf-8")
    ).digest()


def _encode_cookie(payload: dict[str, Any], settings: Settings) -> str:
    body = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    ).decode("ascii").rstrip("=")
    sig = hmac.new(
        _session_secret(settings), body.encode("ascii"), hashlib.sha256
    ).hexdigest()
    return f"{body}.{sig}"


def _decode_cookie(value: str, settings: Settings) -> dict[str, Any] | None:
    if not value or "." not in value:
        return None
    body, sig = value.rsplit(".", 1)
    expected = hmac.new(
        _session_secret(settings), body.encode("ascii"), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return None
    pad = "=" * (-len(body) % 4)
    try:
        payload = json.loads(base64.urlsafe_b64decode(body + pad))
    except (json.JSONDecodeError, ValueError):
        return None
    exp = payload.get("exp")
    if not isinstance(exp, (int, float)) or exp < time.time():
        return None
    jti = payload.get("jti")
    if isinstance(jti, str) and _is_jti_revoked(jti):
        return None
    return payload


# ---------------------------------------------------------------------------
# JTI revocation (logout / forced session invalidation)
# ---------------------------------------------------------------------------

_jti_lock = threading.Lock()
# jti -> expires_at (epoch seconds); purged lazily on writes/reads.
_REVOKED_JTIS: dict[str, float] = {}


def _purge_revoked_jtis_locked(now: float) -> None:
    expired = [jti for jti, exp in _REVOKED_JTIS.items() if exp <= now]
    for jti in expired:
        del _REVOKED_JTIS[jti]


def revoke_jti(jti: str, exp: float) -> None:
    """Revoke a session token id until its own expiry, then let it be pruned."""
    now = time.time()
    with _jti_lock:
        _purge_revoked_jtis_locked(now)
        _REVOKED_JTIS[jti] = float(exp)


def _is_jti_revoked(jti: str) -> bool:
    now = time.time()
    with _jti_lock:
        _purge_revoked_jtis_locked(now)
        return jti in _REVOKED_JTIS


def make_session_cookie(username: str, settings: Settings) -> str:
    now = int(time.time())
    ttl = max(1, settings.session_ttl_hours) * 3600
    payload = {
        "sub": username,
        "username": username,
        "iat": now,
        "exp": now + ttl,
        "jti": secrets.token_urlsafe(16),
    }
    return _encode_cookie(payload, settings)


def cookie_header_value(token: str, settings: Settings) -> str:
    parts = [
        f"{SESSION_COOKIE}={token}",
        "HttpOnly",
        "Path=/",
        "SameSite=Lax",
    ]
    if settings.session_cookie_secure:
        parts.append("Secure")
    max_age = max(1, settings.session_ttl_hours) * 3600
    parts.append(f"Max-Age={max_age}")
    return "; ".join(parts)


def clear_cookie_header_value(settings: Settings | None = None) -> str:
    parts = [f"{SESSION_COOKIE}=", "HttpOnly", "Path=/", "SameSite=Lax"]
    if settings is not None and settings.session_cookie_secure:
        parts.append("Secure")
    parts.append("Max-Age=0")
    return "; ".join(parts)


def verify_local_password(password: str, settings: Settings) -> bool:
    if settings.local_admin_password_hash:
        try:
            return bcrypt.checkpw(
                password.encode("utf-8"),
                settings.local_admin_password_hash.encode("utf-8"),
            )
        except ValueError:
            return False
    if settings.local_admin_password:
        return secrets.compare_digest(password, settings.local_admin_password)
    return False


def parse_ingress_headers(conn: HTTPConnection) -> tuple[str, str | None, str | None] | None:
    user_id = conn.headers.get(INGRESS_USER_ID, "").strip()
    if not user_id:
        return None
    username = conn.headers.get(INGRESS_USER_NAME, "").strip() or None
    display = conn.headers.get(INGRESS_DISPLAY_NAME, "").strip() or None
    return user_id, username, display


def ingress_headers_allowed(conn: HTTPConnection, settings: Settings) -> bool:
    """Gate ingress-header trust to configured proxy IPs/CIDRs.

    The HA Supervisor add-on network is always trusted. Outside the add-on,
    `trusted_proxy_ips` MUST be configured — fail closed with no configured
    allowlist, since trusting ingress headers from an arbitrary source would
    let any caller spoof `X-Remote-User-*` identity. Once configured, only
    matching source IPs are trusted.
    """
    if settings.is_addon:
        return True
    allowed = settings.trusted_proxy_ip_set
    if not allowed:
        return False
    client_ip = conn.client.host if conn.client else None
    if not client_ip:
        return False
    try:
        addr = ipaddress.ip_address(client_ip)
    except ValueError:
        return False
    for cidr in allowed:
        try:
            network = ipaddress.ip_network(cidr, strict=False)
        except ValueError:
            continue
        if addr in network:
            return True
    return False


def _token_session() -> SessionUser:
    return SessionUser(
        user_id="api-token",
        username="api-token",
        display_name="API Token",
        is_admin=True,
        auth_mode="token",
    )


def _supervisor_session() -> SessionUser:
    return SessionUser(
        user_id="supervisor",
        username="supervisor",
        display_name="Supervisor",
        is_admin=True,
        auth_mode="supervisor",
    )


def _client_session(client_id: str, name: str) -> SessionUser:
    return SessionUser(
        user_id=f"client:{client_id}",
        username=name,
        display_name=name,
        is_admin=True,
        auth_mode="client",
    )


def _mcp_session() -> SessionUser:
    """MCP agents authenticate with their own token and are never REST-admin."""
    return SessionUser(
        user_id="mcp",
        username="mcp",
        display_name="MCP Agent",
        is_admin=False,
        auth_mode="mcp",
    )


def _secret_matches(provided: str, secret: str) -> bool:
    if not secret:
        return False
    return hmac.compare_digest(provided, secret)


async def _match_provided_token(provided: str, settings: Settings) -> SessionUser | None:
    if (
        settings.is_addon
        and settings.supervisor_token
        and _secret_matches(provided, settings.supervisor_token)
    ):
        return _supervisor_session()
    if _secret_matches(provided, settings.api_token):
        return _token_session()
    if _secret_matches(provided, settings.mcp_token):
        return _mcp_session()
    from ..auth.api_clients import match_client_token

    # match_client_token holds a lock and does file I/O; keep it off the
    # event loop since this runs on every authenticated request.
    client = await asyncio.to_thread(match_client_token, settings.data_dir, provided)
    if client is not None and client.id:
        return _client_session(client.id, client.name)
    return None


async def parse_bearer_token(conn: HTTPConnection, settings: Settings) -> SessionUser | None:
    auth = conn.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    return await _match_provided_token(auth[7:], settings)


async def parse_query_token(conn: HTTPConnection, settings: Settings) -> SessionUser | None:
    """WebSocket clients pass ?ticket= (preferred) or legacy ?token=.

    Browsers cannot send an Authorization header on WS upgrades, and a
    long-lived bearer token in the URL would leak via logs/history — so the
    dashboard mints a short-lived, single-use ?ticket= instead. ?token=
    remains for backward compatibility with existing integrations.
    """
    ticket = conn.query_params.get("ticket", "").strip()
    if ticket:
        from .ws_tickets import consume_ws_ticket

        user = consume_ws_ticket(ticket)
        if user is not None:
            return user

    token = conn.query_params.get("token", "").strip()
    if not token:
        return None
    log.warning(
        "WebSocket client used legacy ?token= query param — this is "
        "soft-deprecated in favor of the short-lived ?ticket= flow."
    )
    return await _match_provided_token(token, settings)


async def credentials_configured(settings: Settings) -> bool:
    """Local password, env tokens, or minted paired clients lock the API."""
    if settings.local_auth_enabled or settings.api_token or settings.mcp_token:
        return True
    from ..auth.api_clients import has_paired_clients

    # has_paired_clients reads the clients store from disk; keep it off the
    # event loop since this is checked on every gated request.
    return await asyncio.to_thread(has_paired_clients, settings.data_dir)


async def has_auth_lock(settings: Settings) -> bool:
    """True when anonymous LAN-open must be disabled."""
    return bool(settings.ingress_trusted or await credentials_configured(settings))


def parse_local_cookie(conn: HTTPConnection, settings: Settings) -> SessionUser | None:
    raw = conn.cookies.get(SESSION_COOKIE)
    if not raw:
        return None
    payload = _decode_cookie(raw, settings)
    if not payload:
        return None
    username = payload.get("username") or payload.get("sub")
    if not username:
        return None
    if username != settings.local_admin_username:
        return None
    return SessionUser(
        user_id=f"local:{username}",
        username=str(username),
        display_name=str(username),
        is_admin=True,
        auth_mode="local",
    )


async def open_session(settings: Settings) -> SessionUser | None:
    """Anonymous admin session for local dev — opt-in only, and never when locked."""
    if not settings.allow_open_access:
        return None
    if await has_auth_lock(settings):
        return None
    return SessionUser(
        user_id=None,
        username=None,
        display_name=None,
        is_admin=True,
        auth_mode="open",
    )


async def resolve_session(
    conn: HTTPConnection,
    settings: Settings | None = None,
    admin_resolver: Any | None = None,
) -> SessionUser:
    """Resolve the caller identity. Ingress headers take priority over local login."""
    settings = settings or get_settings()

    if settings.ingress_trusted:
        ingress = parse_ingress_headers(conn)
        if ingress and ingress_headers_allowed(conn, settings):
            user_id, username, display = ingress
            is_admin = False
            if user_id in settings.admin_user_id_set:
                is_admin = True
            elif admin_resolver is not None:
                try:
                    is_admin = await admin_resolver.is_admin(user_id)
                except Exception:  # noqa: BLE001
                    log.warning("HA admin lookup failed for %s", user_id, exc_info=True)
                    is_admin = False
            return SessionUser(
                user_id=user_id,
                username=username,
                display_name=display or username,
                is_admin=is_admin,
                auth_mode="ingress",
            )

    local = parse_local_cookie(conn, settings)
    if local:
        return local

    bearer = await parse_bearer_token(conn, settings)
    if bearer:
        return bearer

    if conn.scope.get("type") == "websocket":
        query_token = await parse_query_token(conn, settings)
        if query_token:
            return query_token

    open_ = await open_session(settings)
    if open_:
        return open_

    return ANONYMOUS


def get_session(conn: HTTPConnection) -> SessionUser:
    session = getattr(conn.state, "session", None)
    if isinstance(session, SessionUser):
        return session
    return ANONYMOUS


def is_mcp_plane(session: SessionUser) -> bool:
    """True when the caller authenticated via the MCP (agent) bearer token."""
    return session.auth_mode == "mcp"


def is_operator(session: SessionUser) -> bool:
    """True for authenticated human/system callers, excluding the MCP agent plane."""
    return session.authenticated and not is_mcp_plane(session)


def is_public_api_path(path: str) -> bool:
    return path in PUBLIC_API_PREFIXES


async def requires_auth_gate(path: str, settings: Settings) -> bool:
    if not await credentials_configured(settings):
        return False
    if is_public_api_path(path):
        return False
    if path in _DOC_PATHS:
        return True
    if path.startswith("/api") or path == "/metrics" or path == "/ws":
        return True
    return False


def require_authenticated(request: Request) -> SessionUser:
    session = get_session(request)
    if not session.authenticated:
        raise api_error("api.auth.unauthorized", 401)
    if is_mcp_plane(session):
        raise api_error("api.auth.mcp_not_allowed", 403)
    return session


def require_admin(request: Request) -> SessionUser:
    session = require_authenticated(request)
    if not session.is_admin:
        raise api_error("api.session.admin_required", 403)
    return session


VIEWER_OVERRIDE_FIELDS = frozenset({
    "shadow_mode",
    "pause_engine",
    "pause_shedding",
    "pause_grid_charge",
    "pause_optimization",
    "force_grid_charge",
    "force_shed_off",
    "kill_switch",
})


def assert_override_allowed(session: SessionUser, ov: Override) -> None:
    """Viewers may pause/resume engine and subsystems, force grid charge, toggle shadow/live, and kill switch."""
    if session.is_admin:
        return
    touched = {
        k
        for k, v in ov.model_dump(exclude_none=True).items()
        if v is not None
    }
    if touched - VIEWER_OVERRIDE_FIELDS:
        raise api_error("api.session.admin_required_override", 403)
