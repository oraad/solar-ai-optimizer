"""Session identity: HA ingress headers, local cookie, bearer token, or open dev mode."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import secrets
import time
from dataclasses import dataclass
from typing import Any, Literal

import bcrypt
from fastapi import HTTPException, Request
from starlette.requests import HTTPConnection

from ..i18n import api_error

from .. import __version__
from ..config import Settings, get_settings
from ..models import Override

log = logging.getLogger("api.session")

AuthMode = Literal["ingress", "local", "token", "open", "none"]

SESSION_COOKIE = "solar_session"

INGRESS_USER_ID = "X-Remote-User-Id"
INGRESS_USER_NAME = "X-Remote-User-Name"
INGRESS_DISPLAY_NAME = "X-Remote-User-Display-Name"

# Exact-path match via is_public_api_path(); not a prefix.
PUBLIC_API_PREFIXES = (
    "/api/health",
    "/api/auth/login",
    "/api/auth/logout",
    "/api/auth/status",
)


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
    return payload


def make_session_cookie(username: str, settings: Settings) -> str:
    now = int(time.time())
    ttl = max(1, settings.session_ttl_hours) * 3600
    payload = {
        "sub": username,
        "username": username,
        "iat": now,
        "exp": now + ttl,
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


def clear_cookie_header_value() -> str:
    return f"{SESSION_COOKIE}=; HttpOnly; Path=/; SameSite=Lax; Max-Age=0"


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


def _token_session() -> SessionUser:
    return SessionUser(
        user_id="api-token",
        username="api-token",
        display_name="API Token",
        is_admin=True,
        auth_mode="token",
    )


def _secret_matches(provided: str, secret: str) -> bool:
    if not secret:
        return False
    return hmac.compare_digest(provided, secret)


def parse_bearer_token(conn: HTTPConnection, settings: Settings) -> SessionUser | None:
    auth = conn.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    provided = auth[7:]
    for secret in (settings.api_token, settings.mcp_token):
        if _secret_matches(provided, secret):
            return _token_session()
    return None


def parse_query_token(conn: HTTPConnection, settings: Settings) -> SessionUser | None:
    """WebSocket clients pass ?token= when browsers cannot send Authorization."""
    token = conn.query_params.get("token", "").strip()
    if not token:
        return None
    for secret in (settings.api_token, settings.mcp_token):
        if _secret_matches(token, secret):
            return _token_session()
    return None


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


def open_session(settings: Settings) -> SessionUser | None:
    if (
        settings.local_auth_enabled
        or settings.api_token
        or settings.mcp_token
        or settings.ingress_trusted
    ):
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
        if ingress:
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

    bearer = parse_bearer_token(conn, settings)
    if bearer:
        return bearer

    if conn.scope.get("type") == "websocket":
        query_token = parse_query_token(conn, settings)
        if query_token:
            return query_token

    open_ = open_session(settings)
    if open_:
        return open_

    return ANONYMOUS


def get_session(conn: HTTPConnection) -> SessionUser:
    session = getattr(conn.state, "session", None)
    if isinstance(session, SessionUser):
        return session
    return ANONYMOUS


def is_public_api_path(path: str) -> bool:
    return path in PUBLIC_API_PREFIXES


def requires_auth_gate(path: str, settings: Settings) -> bool:
    if (
        not settings.local_auth_enabled
        and not settings.api_token
        and not settings.mcp_token
    ):
        return False
    if is_public_api_path(path):
        return False
    if path.startswith("/api") or path == "/metrics" or path == "/ws":
        return True
    return False


def require_authenticated(request: Request) -> SessionUser:
    session = get_session(request)
    if not session.authenticated:
        raise api_error("api.auth.unauthorized", 401)
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
