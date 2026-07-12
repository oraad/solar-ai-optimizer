"""Hassio discovery publish, HA bootstrap, and HA credential save guards."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.config import Settings
from app.ha import oauth as ha_oauth
from app.orchestrator import Orchestrator
from app.services.hassio_discovery import (
    addon_hostname_from_slug,
    publish_hassio_discovery,
)


def test_addon_hostname_from_slug():
    assert addon_hostname_from_slug("solar_ai_optimizer") == "solar-ai-optimizer"


@pytest.mark.asyncio
async def test_publish_hassio_discovery_posts_uri(tmp_path: Path):
    settings = Settings(
        ha_token="",
        database_url="sqlite+aiosqlite:///:memory:",
        data_dir=str(tmp_path),
        **{"SUPERVISOR_TOKEN": "sup-token"},
    )

    class FakeResponse:
        def __init__(self, status_code: int = 200, payload: dict | None = None):
            self.status_code = status_code
            self._payload = payload or {}
            self.text = ""

        @property
        def is_success(self) -> bool:
            return 200 <= self.status_code < 300

        def json(self):
            return self._payload

    info_resp = FakeResponse(
        200, {"data": {"hostname": "solar-ai-optimizer", "slug": "solar_ai_optimizer"}}
    )
    post_resp = FakeResponse(200, {"data": {"uuid": "abc"}})

    client = AsyncMock()
    client.__aenter__.return_value = client
    client.__aexit__.return_value = None
    client.get = AsyncMock(return_value=info_resp)
    client.post = AsyncMock(return_value=post_resp)

    with patch("app.services.hassio_discovery.httpx.AsyncClient", return_value=client):
        await publish_hassio_discovery(settings)

    client.post.assert_awaited_once()
    args, kwargs = client.post.call_args
    assert args[0] == "http://supervisor/discovery"
    assert kwargs["headers"]["Authorization"] == "Bearer sup-token"
    body = kwargs["json"]
    assert body["service"] == "solar_ai_optimizer"
    assert body["config"]["uri"] == "http://solar-ai-optimizer:8000"
    assert body["config"]["install_id"]


@pytest.mark.asyncio
async def test_publish_hassio_discovery_soft_fails(tmp_path: Path):
    settings = Settings(
        ha_token="",
        database_url="sqlite+aiosqlite:///:memory:",
        data_dir=str(tmp_path),
        **{"SUPERVISOR_TOKEN": "sup-token"},
    )
    with patch(
        "app.services.hassio_discovery.httpx.AsyncClient",
        side_effect=httpx.ConnectError("down"),
    ):
        await publish_hassio_discovery(settings)  # must not raise


def test_sanitize_strips_ha_creds_on_addon():
    orch = object.__new__(Orchestrator)
    orch.settings = Settings(
        ha_token="",
        database_url="sqlite+aiosqlite:///:memory:",
        data_dir="/tmp",
        **{"SUPERVISOR_TOKEN": "sup"},
    )
    patch = {"ha": {"base_url": "http://evil", "token": "llat", "verify_ssl": True}}
    out = orch._sanitize_config_patch(patch)
    assert "ha" in out
    assert "token" not in out["ha"]
    assert "base_url" not in out["ha"]
    assert out["ha"]["verify_ssl"] is True


def test_sanitize_strips_token_when_oauth_live(tmp_path: Path):
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
        ha_token="",
        database_url="sqlite+aiosqlite:///:memory:",
        data_dir=str(tmp_path),
    )
    patch = {"ha": {"base_url": "http://yaml:8123", "token": "should-ignore"}}
    out = orch._sanitize_config_patch(patch)
    assert out["ha"]["base_url"] == "http://yaml:8123"
    assert "token" not in out["ha"]


def test_sanitize_keeps_token_when_no_oauth(tmp_path: Path):
    orch = object.__new__(Orchestrator)
    orch.settings = Settings(
        ha_token="",
        database_url="sqlite+aiosqlite:///:memory:",
        data_dir=str(tmp_path),
    )
    patch = {"ha": {"base_url": "http://yaml:8123", "token": "llat-token"}}
    out = orch._sanitize_config_patch(patch)
    assert out["ha"]["token"] == "llat-token"


@pytest.mark.asyncio
async def test_ha_bootstrap_validates_and_persists(tmp_path: Path, monkeypatch):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("battery:\n  capacity_kwh: 10\n", encoding="utf-8")
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setenv("CONFIG_PATH", str(cfg))
    monkeypatch.setenv("DATA_DIR", str(data))
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{data / 'test.db'}")
    monkeypatch.setenv("HA_TOKEN", "")
    monkeypatch.setenv("HA_BASE_URL", "http://127.0.0.1:9")
    monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)

    from app.config import get_settings

    get_settings.cache_clear()

    class FakeResponse:
        status_code = 200

    client = AsyncMock()
    client.__aenter__.return_value = client
    client.__aexit__.return_value = None
    client.get = AsyncMock(return_value=FakeResponse())

    orch = MagicMock()
    orch.apply_ha_llat = AsyncMock(return_value=None)

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api.routes import router
    from app.api.session import SessionUser

    app = FastAPI()
    app.include_router(router)
    app.state.orchestrator = orch

    async def _admin():
        return SessionUser(
            user_id="admin",
            username="admin",
            display_name="admin",
            is_admin=True,
            auth_mode="local",
        )

    from app.api import session as session_mod

    app.dependency_overrides[session_mod.require_admin] = _admin

    with patch("httpx.AsyncClient", return_value=client):
        with TestClient(app) as tc:
            res = tc.post(
                "/api/ha/bootstrap",
                json={
                    "ha_base_url": "http://ha.local:8123",
                    "ha_token": "llat-secret",
                },
            )

    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["access_token"] == "llat-secret"
    assert body["ha_auth_mode"] == "llat"
    assert body["install_id"]
    orch.apply_ha_llat.assert_awaited_once_with(
        base_url="http://ha.local:8123",
        token="llat-secret",
    )


@pytest.mark.asyncio
async def test_ha_bootstrap_rejects_bad_token(tmp_path: Path, monkeypatch):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("battery:\n  capacity_kwh: 10\n", encoding="utf-8")
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setenv("CONFIG_PATH", str(cfg))
    monkeypatch.setenv("DATA_DIR", str(data))
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{data / 'test.db'}")
    monkeypatch.setenv("HA_TOKEN", "")
    monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)

    from app.config import get_settings

    get_settings.cache_clear()

    class FakeResponse:
        status_code = 401

    client = AsyncMock()
    client.__aenter__.return_value = client
    client.__aexit__.return_value = None
    client.get = AsyncMock(return_value=FakeResponse())

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api.routes import router
    from app.api.session import SessionUser

    app = FastAPI()
    app.include_router(router)
    app.state.orchestrator = MagicMock()

    async def _admin():
        return SessionUser(
            user_id="admin",
            username="admin",
            display_name="admin",
            is_admin=True,
            auth_mode="local",
        )

    from app.api import session as session_mod

    app.dependency_overrides[session_mod.require_admin] = _admin

    with patch("httpx.AsyncClient", return_value=client):
        with TestClient(app) as tc:
            res = tc.post(
                "/api/ha/bootstrap",
                json={
                    "ha_base_url": "http://ha.local:8123",
                    "ha_token": "bad",
                },
            )

    assert res.status_code == 400
