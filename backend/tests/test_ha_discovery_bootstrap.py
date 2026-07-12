"""Hassio discovery publish and HA credential save guards."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

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


def test_sanitize_always_strips_token(tmp_path: Path):
    orch = object.__new__(Orchestrator)
    orch.settings = Settings(
        ha_token="",
        database_url="sqlite+aiosqlite:///:memory:",
        data_dir=str(tmp_path),
    )
    patch = {"ha": {"base_url": "http://yaml:8123", "token": "llat-token", "verify_ssl": False}}
    out = orch._sanitize_config_patch(patch)
    assert out["ha"]["base_url"] == "http://yaml:8123"
    assert out["ha"]["verify_ssl"] is False
    assert "token" not in out["ha"]


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
