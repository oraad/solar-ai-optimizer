"""Tests for Solar → Home Assistant IndieAuth and credential resolve order."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.config import Settings
from app.ha import oauth as ha_oauth
from app.orchestrator import Orchestrator


def test_oauth_status_disconnected(tmp_path: Path):
    status = ha_oauth.oauth_status(tmp_path)
    assert status["connected"] is False
    assert status["auth_mode"] is None
    assert status["degraded"] is False


def test_start_authorize_pkce_and_state(tmp_path: Path):
    started = ha_oauth.start_authorize(
        tmp_path,
        ha_base_url="http://192.168.1.5:8123",
        public_base_url="http://192.168.1.10:8000",
        verify_ssl=False,
    )
    assert "state=" in started.authorize_url
    assert "code_challenge=" in started.authorize_url
    assert "code_challenge_method=S256" in started.authorize_url
    assert started.state
    pending = tmp_path / "ha_oauth_pending.json"
    assert pending.is_file()
    payload = __import__("json").loads(pending.read_text(encoding="utf-8"))
    assert payload["public_base_url"] == "http://192.168.1.10:8000"
    assert payload["code_verifier"]
    assert payload["verify_ssl"] is False


@pytest.mark.asyncio
async def test_ensure_access_token_invalid_grant_clears_store(tmp_path: Path):
    ha_oauth._atomic_write(
        ha_oauth.oauth_path(tmp_path),
        {
            "access_token": "old",
            "refresh_token": "refresh",
            "expires_at": "2000-01-01T00:00:00Z",
            "ha_base_url": "http://ha.local:8123",
            "public_base_url": "http://solar.local:8000",
            "degraded": False,
        },
    )

    class FakeResponse:
        status_code = 400

        def json(self):
            return {"error": "invalid_grant"}

    with patch("app.ha.oauth.httpx.AsyncClient") as client_cls:
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.__aexit__.return_value = None
        client.post = AsyncMock(return_value=FakeResponse())
        client_cls.return_value = client

        token = await ha_oauth.ensure_access_token(tmp_path, verify_ssl=True)

    assert token is None
    assert ha_oauth.load_oauth(tmp_path) is None


def test_resolve_ha_addon_supervisor_wins():
    orch = object.__new__(Orchestrator)
    orch.settings = Settings(
        ha_token="env-token",
        database_url="sqlite+aiosqlite:///:memory:",
        data_dir="/tmp",
        **{"SUPERVISOR_TOKEN": "supervisor-secret"},
    )
    orch.cfg = MagicMock()
    orch.cfg.ha.base_url = "http://yaml:8123"
    orch.cfg.ha.token = "yaml-token"
    orch.cfg.ha.verify_ssl = False

    base, token, verify = orch._resolve_ha()
    assert base == "http://supervisor/core"
    assert token == "supervisor-secret"
    assert verify is True


def test_resolve_ha_oauth_before_env(tmp_path: Path):
    ha_oauth._atomic_write(
        ha_oauth.oauth_path(tmp_path),
        {
            "access_token": "oauth-access",
            "refresh_token": "oauth-refresh",
            "expires_at": "2099-01-01T00:00:00Z",
            "ha_base_url": "http://oauth-ha:8123",
            "public_base_url": "http://solar:8000",
            "degraded": False,
        },
    )

    orch = object.__new__(Orchestrator)
    orch.settings = Settings(
        ha_token="env-token",
        ha_base_url="http://env-ha:8123",
        database_url="sqlite+aiosqlite:///:memory:",
        data_dir=str(tmp_path),
        is_addon=False,
    )
    orch.cfg = MagicMock()
    orch.cfg.ha.base_url = "http://yaml:8123"
    orch.cfg.ha.token = "yaml-token-ignored"
    orch.cfg.ha.verify_ssl = False

    base, token, verify = orch._resolve_ha()
    assert base == "http://oauth-ha:8123"
    assert token == "oauth-access"
    assert verify is False
    assert orch.resolve_ha_auth_mode() == "oauth"


def test_resolve_ha_degraded_oauth_falls_to_env(tmp_path: Path):
    ha_oauth._atomic_write(
        ha_oauth.oauth_path(tmp_path),
        {
            "access_token": "oauth-access",
            "refresh_token": "oauth-refresh",
            "expires_at": "2099-01-01T00:00:00Z",
            "ha_base_url": "http://oauth-ha:8123",
            "public_base_url": "http://solar:8000",
            "degraded": True,
        },
    )

    orch = object.__new__(Orchestrator)
    orch.settings = Settings(
        ha_token="env-token",
        ha_base_url="http://env-ha:8123",
        database_url="sqlite+aiosqlite:///:memory:",
        data_dir=str(tmp_path),
        is_addon=False,
    )
    orch.cfg = MagicMock()
    orch.cfg.ha.base_url = "http://yaml:8123"
    orch.cfg.ha.token = "yaml-token-ignored"
    orch.cfg.ha.verify_ssl = True

    base, token, verify = orch._resolve_ha()
    # YAML LLAT ignored; use cfg base_url if set, else env — token from env only
    assert token == "env-token"
    assert orch.resolve_ha_auth_mode() == "env"
    assert verify is True


def _seed_pending(tmp_path: Path, *, verify_ssl: bool = True) -> str:
    started = ha_oauth.start_authorize(
        tmp_path,
        ha_base_url="http://ha.local:8123",
        public_base_url="http://solar.local:8000",
        verify_ssl=verify_ssl,
    )
    return started.state


@pytest.mark.asyncio
async def test_finish_authorize_maps_403_to_ha_forbidden(tmp_path: Path):
    state = _seed_pending(tmp_path)

    class FakeResponse:
        status_code = 403
        text = "403: Forbidden"

        def json(self):
            return {"error": "access_denied", "error_description": "Banned"}

    with patch("app.ha.oauth.httpx.AsyncClient") as client_cls:
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.__aexit__.return_value = None
        client.post = AsyncMock(return_value=FakeResponse())
        client_cls.return_value = client

        with pytest.raises(ha_oauth.OAuthError) as excinfo:
            await ha_oauth.finish_authorize(tmp_path, code="abc", state=state)

    assert excinfo.value.code == "ha_forbidden"
    assert "403" in (excinfo.value.detail or "")
    html = ha_oauth.callback_failure_html(excinfo.value)
    assert "ip_bans.yaml" in html
    assert "ha_forbidden" in html


@pytest.mark.asyncio
async def test_finish_authorize_maps_400_with_detail(tmp_path: Path):
    state = _seed_pending(tmp_path)

    class FakeResponse:
        status_code = 400
        text = '{"error":"invalid_request","error_description":"Invalid code"}'

        def json(self):
            return {"error": "invalid_request", "error_description": "Invalid code"}

    with patch("app.ha.oauth.httpx.AsyncClient") as client_cls:
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.__aexit__.return_value = None
        client.post = AsyncMock(return_value=FakeResponse())
        client_cls.return_value = client

        with pytest.raises(ha_oauth.OAuthError) as excinfo:
            await ha_oauth.finish_authorize(tmp_path, code="bad", state=state)

    assert excinfo.value.code == "token_exchange_failed"
    assert "Invalid code" in (excinfo.value.detail or "")


@pytest.mark.asyncio
async def test_finish_authorize_maps_connect_error(tmp_path: Path):
    state = _seed_pending(tmp_path)

    with patch("app.ha.oauth.httpx.AsyncClient") as client_cls:
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.__aexit__.return_value = None
        client.post = AsyncMock(side_effect=httpx.ConnectError("Name or service not known"))
        client_cls.return_value = client

        with pytest.raises(ha_oauth.OAuthError) as excinfo:
            await ha_oauth.finish_authorize(tmp_path, code="abc", state=state)

    assert excinfo.value.code == "ha_unreachable"


@pytest.mark.asyncio
async def test_finish_authorize_uses_pending_verify_ssl(tmp_path: Path):
    state = _seed_pending(tmp_path, verify_ssl=False)

    class FakeResponse:
        status_code = 200

        def json(self):
            return {
                "access_token": "access",
                "refresh_token": "refresh",
                "expires_in": 1800,
                "token_type": "Bearer",
            }

    with patch("app.ha.oauth.httpx.AsyncClient") as client_cls:
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.__aexit__.return_value = None
        client.post = AsyncMock(return_value=FakeResponse())
        client_cls.return_value = client

        status = await ha_oauth.finish_authorize(
            tmp_path, code="abc", state=state, verify_ssl=True
        )

    assert status["connected"] is True
    # Pending verify_ssl=False must win over the True fallback argument.
    _, kwargs = client_cls.call_args
    assert kwargs.get("verify") is False


@pytest.mark.asyncio
async def test_finish_authorize_revalidates_ssrf_on_pending_url(tmp_path: Path):
    """The pending ha_base_url is re-checked at /callback time, not just at
    /start — a blocked address (even if it somehow ended up on disk) must
    not reach the token exchange."""
    from datetime import UTC, datetime, timedelta

    state = "revalidate-state"
    ha_oauth._atomic_write(
        ha_oauth.pending_path(tmp_path),
        {
            "state": state,
            "code_verifier": "verifier",
            "ha_base_url": "http://169.254.169.254:8123",
            "public_base_url": "http://solar.local:8000",
            "redirect_uri": "http://solar.local:8000/api/ha/oauth/callback",
            "verify_ssl": True,
            "expires_at": (datetime.now(UTC) + timedelta(minutes=5)).isoformat().replace("+00:00", "Z"),
        },
    )

    with patch("app.ha.oauth.httpx.AsyncClient") as client_cls:
        with pytest.raises(ha_oauth.OAuthError) as excinfo:
            await ha_oauth.finish_authorize(
                tmp_path, code="abc", state=state, allow_private=True
            )
        # Blocked before any HTTP call was attempted.
        client_cls.assert_not_called()

    assert excinfo.value.code == "ha_url_blocked"
    assert not ha_oauth.pending_path(tmp_path).is_file()


@pytest.mark.asyncio
async def test_retry_ha_connection_reloads_credentials(tmp_path: Path):
    """Retry must rebuild HAClient from disk, not reuse a stale in-memory token."""
    ha_oauth._atomic_write(
        ha_oauth.oauth_path(tmp_path),
        {
            "access_token": "fresh-oauth-token",
            "refresh_token": "refresh",
            "expires_at": "2099-01-01T00:00:00Z",
            "ha_base_url": "http://ha.local:8123",
            "public_base_url": "http://solar.local:8000",
            "degraded": False,
        },
    )
    orch = object.__new__(Orchestrator)
    orch.settings = Settings(
        ha_token="stale-env",
        ha_base_url="http://ha.local:8123",
        database_url="sqlite+aiosqlite:///:memory:",
        data_dir=str(tmp_path),
    )
    orch.cfg = MagicMock()
    orch.cfg.ha.base_url = "http://ha.local:8123"
    orch.cfg.ha.verify_ssl = True
    orch._stream_task = None
    orch._admin_resolver = None
    orch.ha = MagicMock()
    orch.ha.aclose = AsyncMock()
    orch.ha.ping = AsyncMock(return_value=True)
    orch.ha.ws_diagnostics = MagicMock(
        return_value={
            "ha_ws_error_class": "none",
            "ha_ws_last_error": None,
            "ha_ws_circuit_open": False,
            "ha_ws_fail_count": 0,
            "ha_ws_backoff_seconds": 0,
        }
    )
    orch.heartbeat = MagicMock()
    orch.adapter = MagicMock()
    orch.collector = MagicMock()
    orch.collector.prime = AsyncMock()
    orch.collector.run_stream_safe = AsyncMock()
    orch._build_engine_components = MagicMock()
    orch.resolve_ha_auth_mode = MagicMock(return_value="oauth")

    result = await orch.retry_ha_connection()

    assert orch.ha._token == "fresh-oauth-token"  # type: ignore[attr-defined]
    assert result["ok"] is True
    assert result["ha_auth_mode"] == "oauth"


@pytest.mark.asyncio
async def test_oauth_callback_reloads_ha_credentials(tmp_path: Path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api.ha_oauth_routes import router
    from app.config import get_settings

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("HA_TOKEN", "")
    get_settings.cache_clear()

    started = ha_oauth.start_authorize(
        tmp_path,
        ha_base_url="http://ha.local:8123",
        public_base_url="http://solar.local:8000",
        verify_ssl=False,
    )

    class FakeResponse:
        status_code = 200

        def json(self):
            return {
                "access_token": "new-access",
                "refresh_token": "new-refresh",
                "expires_in": 1800,
                "token_type": "Bearer",
            }

    orch = MagicMock()
    orch.reload_ha_credentials = AsyncMock()

    app = FastAPI()
    app.state.orchestrator = orch
    app.include_router(router)

    with patch("app.ha.oauth.httpx.AsyncClient") as client_cls:
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.__aexit__.return_value = None
        client.post = AsyncMock(return_value=FakeResponse())
        client_cls.return_value = client

        with TestClient(app) as client_http:
            res = client_http.get(
                f"/api/ha/oauth/callback?code=abc&state={started.state}"
            )

    assert res.status_code == 200
    assert "Connected" in res.text
    orch.reload_ha_credentials.assert_awaited_once()
    stored = ha_oauth.load_oauth(tmp_path)
    assert stored is not None
    assert stored["access_token"] == "new-access"


@pytest.mark.asyncio
async def test_oauth_disconnect_reloads_ha_credentials(tmp_path: Path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api.auth import AuthGateMiddleware, UserContextMiddleware
    from app.api.ha_oauth_routes import router
    from app.config import get_settings

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("HA_TOKEN", "")
    monkeypatch.delenv("API_TOKEN", raising=False)
    monkeypatch.delenv("LOCAL_ADMIN_PASSWORD", raising=False)
    monkeypatch.delenv("LOCAL_ADMIN_PASSWORD_HASH", raising=False)
    monkeypatch.setenv("ALLOW_OPEN_ACCESS", "true")
    get_settings.cache_clear()

    ha_oauth._atomic_write(
        ha_oauth.oauth_path(tmp_path),
        {
            "access_token": "access",
            "refresh_token": "refresh",
            "expires_at": "2099-01-01T00:00:00Z",
            "ha_base_url": "http://ha.local:8123",
            "public_base_url": "http://solar.local:8000",
            "degraded": False,
        },
    )

    orch = MagicMock()
    orch.reload_ha_credentials = AsyncMock()

    app = FastAPI()
    app.state.orchestrator = orch
    app.state.admin_resolver = AsyncMock()
    app.add_middleware(AuthGateMiddleware)
    app.add_middleware(UserContextMiddleware)
    app.include_router(router)

    with TestClient(app) as client_http:
        res = client_http.delete("/api/ha/oauth/disconnect")

    assert res.status_code == 200
    assert res.json() == {"ok": True}
    assert ha_oauth.load_oauth(tmp_path) is None
    orch.reload_ha_credentials.assert_awaited_once()
