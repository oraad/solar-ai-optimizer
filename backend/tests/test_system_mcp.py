"""Admin MCP settings and lifecycle APIs."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.auth import AuthGateMiddleware, UserContextMiddleware
from app.api.system_mcp import router
from app.config import get_settings
from app.mcp.credentials import read_mcp_env
from tests.conftest_auth import clear_auth_env


@pytest.fixture
def mcp_api_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setenv("DATA_DIR", str(data))
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{data / 't.db'}")
    monkeypatch.setenv("HA_TOKEN", "")
    monkeypatch.setenv("HA_BASE_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("SELF_UPDATE_ENABLED", "true")
    clear_auth_env(monkeypatch)
    get_settings.cache_clear()

    app = FastAPI()
    app.state.orchestrator = MagicMock()
    app.state.admin_resolver = AsyncMock()
    app.state.mcp_server = None
    app.add_middleware(AuthGateMiddleware)
    app.add_middleware(UserContextMiddleware)
    app.include_router(router)
    with TestClient(app) as client:
        yield client, data


def test_get_mcp_settings_standalone(mcp_api_client):
    client, _data = mcp_api_client
    with patch("app.api.system_mcp._can_apply", return_value=True):
        res = client.get("/api/system/mcp")
    assert res.status_code == 200
    body = res.json()
    assert body["editable"] is True
    assert body["enabled"] is False
    assert "token" not in body
    assert body["pending"]["mcp_env"] is False


def test_put_mcp_writes_env_and_masks_token(mcp_api_client):
    client, data = mcp_api_client
    with patch("app.api.system_mcp._can_apply", return_value=True):
        res = client.put(
            "/api/system/mcp",
            json={"enabled": True, "token": "agent-secret"},
        )
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["restart_required"] is True
    assert body["pending"]["mcp_env"] is True
    assert body.get("token") is None
    stored = read_mcp_env(data)
    assert stored["MCP_ENABLED"] == "true"
    assert stored["MCP_TOKEN"] == "agent-secret"


def test_put_generate_token_returns_once(mcp_api_client):
    client, data = mcp_api_client
    with patch("app.api.system_mcp._can_apply", return_value=True):
        res = client.put(
            "/api/system/mcp",
            json={"enabled": True, "generate_token": True},
        )
    assert res.status_code == 200
    body = res.json()
    assert body["token"]
    assert len(body["token"]) == 64
    assert read_mcp_env(data)["MCP_TOKEN"] == body["token"]


def test_put_addon_forbidden(mcp_api_client, monkeypatch):
    client, _data = mcp_api_client
    monkeypatch.setenv("SUPERVISOR_TOKEN", "sup")
    monkeypatch.setenv("ADMIN_USER_IDS", "ha-admin")
    get_settings.cache_clear()
    res = client.put(
        "/api/system/mcp",
        json={"enabled": True, "token": "x"},
        headers={
            "X-Remote-User-Id": "ha-admin",
            "X-Remote-User-Name": "admin",
        },
    )
    assert res.status_code == 403


def test_restart_requires_capability(mcp_api_client):
    client, _data = mcp_api_client
    with patch("app.api.system_mcp._can_apply", return_value=False):
        res = client.post("/api/system/restart")
    assert res.status_code == 503


def test_restart_calls_docker(mcp_api_client):
    client, _data = mcp_api_client
    fake = MagicMock(returncode=0, stderr="", stdout="solar-optimizer\n")
    with (
        patch("app.api.system_mcp._can_apply", return_value=True),
        patch("app.api.system_mcp._docker_cli_available", return_value=True),
        patch("app.api.system_mcp._update_in_progress", return_value=False),
        patch("app.api.system_mcp.subprocess.run", return_value=fake) as run,
    ):
        res = client.post("/api/system/restart")
    assert res.status_code == 200
    assert res.json()["action"] == "restart"
    assert run.call_args[0][0][:2] == ["docker", "restart"]
