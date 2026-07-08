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


def test_resolve_ha_oauth_before_yaml_llat(tmp_path: Path):
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
        database_url="sqlite+aiosqlite:///:memory:",
        data_dir=str(tmp_path),
        is_addon=False,
    )
    orch.cfg = MagicMock()
    orch.cfg.ha.base_url = "http://yaml:8123"
    orch.cfg.ha.token = "yaml-token"
    orch.cfg.ha.verify_ssl = False

    base, token, verify = orch._resolve_ha()
    assert base == "http://oauth-ha:8123"
    assert token == "oauth-access"
    assert verify is False


def test_resolve_ha_degraded_oauth_skipped_for_yaml(tmp_path: Path):
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
        database_url="sqlite+aiosqlite:///:memory:",
        data_dir=str(tmp_path),
        is_addon=False,
    )
    orch.cfg = MagicMock()
    orch.cfg.ha.base_url = "http://yaml:8123"
    orch.cfg.ha.token = "yaml-token"
    orch.cfg.ha.verify_ssl = True

    base, token, verify = orch._resolve_ha()
    assert base == "http://yaml:8123"
    assert token == "yaml-token"
    assert verify is True
