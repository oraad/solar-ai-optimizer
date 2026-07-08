"""IndieAuth (OAuth) client for Solar → Home Assistant."""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx

log = logging.getLogger("ha.oauth")

OAUTH_FILENAME = "ha_oauth.json"
PENDING_FILENAME = "ha_oauth_pending.json"
DEFAULT_ACCESS_TTL = 1800


def oauth_path(data_dir: Path | str) -> Path:
    return Path(data_dir) / OAUTH_FILENAME


def pending_path(data_dir: Path | str) -> Path:
    return Path(data_dir) / PENDING_FILENAME


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
    try:
        path.chmod(0o600)
    except OSError:
        pass


def normalize_public_base_url(url: str) -> str:
    cleaned = url.strip().rstrip("/")
    if not cleaned.startswith(("http://", "https://")):
        raise ValueError("public_base_url must start with http:// or https://")
    return cleaned


def load_oauth(data_dir: Path | str) -> dict[str, Any] | None:
    path = oauth_path(data_dir)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def clear_oauth(data_dir: Path | str) -> None:
    oauth_path(data_dir).unlink(missing_ok=True)
    pending_path(data_dir).unlink(missing_ok=True)


def oauth_status(data_dir: Path | str) -> dict[str, Any]:
    data = load_oauth(data_dir)
    if not data:
        return {
            "connected": False,
            "auth_mode": None,
            "expires_at": None,
            "public_base_url": None,
            "ha_base_url": None,
            "degraded": False,
        }
    return {
        "connected": bool(data.get("refresh_token")),
        "auth_mode": "oauth",
        "expires_at": data.get("expires_at"),
        "public_base_url": data.get("public_base_url"),
        "ha_base_url": data.get("ha_base_url"),
        "degraded": bool(data.get("degraded")),
    }


@dataclass
class AuthorizeStart:
    authorize_url: str
    state: str
    expires_at: str


def start_authorize(
    data_dir: Path | str,
    *,
    ha_base_url: str,
    public_base_url: str,
) -> AuthorizeStart:
    public = normalize_public_base_url(public_base_url)
    ha = ha_base_url.strip().rstrip("/")
    state = secrets.token_urlsafe(24)
    verifier = _b64url(secrets.token_bytes(32))
    challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
    redirect_uri = f"{public}/api/ha/oauth/callback"
    expires = _utc_now() + timedelta(minutes=10)
    _atomic_write(
        pending_path(data_dir),
        {
            "state": state,
            "code_verifier": verifier,
            "ha_base_url": ha,
            "public_base_url": public,
            "redirect_uri": redirect_uri,
            "expires_at": _iso(expires),
        },
    )
    query = urlencode(
        {
            "client_id": public,
            "redirect_uri": redirect_uri,
            "state": state,
            "response_type": "code",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    )
    return AuthorizeStart(
        authorize_url=f"{ha}/auth/authorize?{query}",
        state=state,
        expires_at=_iso(expires),
    )


async def finish_authorize(
    data_dir: Path | str,
    *,
    code: str,
    state: str,
    verify_ssl: bool = True,
) -> dict[str, Any]:
    pending_file = pending_path(data_dir)
    if not pending_file.is_file():
        raise OAuthError("missing_pending")
    try:
        pending = json.loads(pending_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise OAuthError("missing_pending") from exc
    if not isinstance(pending, dict) or pending.get("state") != state:
        raise OAuthError("invalid_state")
    try:
        expires = datetime.fromisoformat(
            str(pending.get("expires_at")).replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise OAuthError("expired") from exc
    if expires <= _utc_now():
        pending_file.unlink(missing_ok=True)
        raise OAuthError("expired")

    ha = str(pending["ha_base_url"]).rstrip("/")
    token_url = f"{ha}/auth/token"
    form = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": pending["public_base_url"],
        "redirect_uri": pending["redirect_uri"],
        "code_verifier": pending["code_verifier"],
    }
    async with httpx.AsyncClient(verify=verify_ssl, timeout=30.0) as client:
        res = await client.post(token_url, data=form)
    if res.status_code >= 400:
        log.warning("HA token exchange failed: %s %s", res.status_code, res.text[:200])
        raise OAuthError("token_exchange_failed")
    body = res.json()
    access = body.get("access_token")
    refresh = body.get("refresh_token")
    if not access or not refresh:
        raise OAuthError("token_exchange_failed")
    expires_in = int(body.get("expires_in") or DEFAULT_ACCESS_TTL)
    expires_at = _utc_now() + timedelta(seconds=max(60, expires_in - 60))
    payload = {
        "access_token": access,
        "refresh_token": refresh,
        "expires_at": _iso(expires_at),
        "ha_base_url": ha,
        "public_base_url": pending["public_base_url"],
        "token_type": body.get("token_type") or "Bearer",
        "degraded": False,
    }
    _atomic_write(oauth_path(data_dir), payload)
    pending_file.unlink(missing_ok=True)
    return oauth_status(data_dir)


async def ensure_access_token(
    data_dir: Path | str,
    *,
    verify_ssl: bool = True,
) -> str | None:
    """Return a usable access token, refreshing when needed."""
    data = load_oauth(data_dir)
    if not data or not data.get("refresh_token"):
        return None
    expires_raw = data.get("expires_at")
    access = data.get("access_token")
    need_refresh = not access
    if expires_raw and not need_refresh:
        try:
            expires = datetime.fromisoformat(str(expires_raw).replace("Z", "+00:00"))
            need_refresh = expires <= _utc_now()
        except ValueError:
            need_refresh = True
    if not need_refresh and isinstance(access, str):
        return access

    ha = str(data.get("ha_base_url") or "").rstrip("/")
    if not ha:
        return None
    form = {
        "grant_type": "refresh_token",
        "refresh_token": data["refresh_token"],
        "client_id": data.get("public_base_url"),
    }
    try:
        async with httpx.AsyncClient(verify=verify_ssl, timeout=30.0) as client:
            res = await client.post(f"{ha}/auth/token", data=form)
    except httpx.HTTPError:
        log.warning("HA token refresh network error", exc_info=True)
        return access if isinstance(access, str) else None
    if res.status_code >= 400:
        log.warning("HA token refresh failed: %s", res.status_code)
        data["degraded"] = True
        _atomic_write(oauth_path(data_dir), data)
        if res.status_code in (400, 401):
            # invalid_grant — drop tokens
            clear_oauth(data_dir)
            return None
        return access if isinstance(access, str) else None
    body = res.json()
    new_access = body.get("access_token")
    if not new_access:
        return None
    expires_in = int(body.get("expires_in") or DEFAULT_ACCESS_TTL)
    data["access_token"] = new_access
    if body.get("refresh_token"):
        data["refresh_token"] = body["refresh_token"]
    data["expires_at"] = _iso(_utc_now() + timedelta(seconds=max(60, expires_in - 60)))
    data["degraded"] = False
    _atomic_write(oauth_path(data_dir), data)
    return str(new_access)


class OAuthError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code
