"""GET/POST /api/system/update — release checks and self-update gates."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import __version__
from app.api.auth import AuthGateMiddleware, UserContextMiddleware
from app.api.system_update import router as system_update_router
from app.models import SystemStatus, utcnow


@pytest.fixture
def update_client(monkeypatch, tmp_path):
    orch = MagicMock()
    orch.build_status.return_value = SystemStatus(
        ha_connected=True,
        telemetry_stale=False,
        telemetry_age_seconds=1.0,
        forecast_misconfigured=False,
        forecast_degraded=False,
        engine_mode="rules",
        engine_active="rules",
        shadow_mode=True,
        paused=False,
        last_updated=utcnow(),
    )
    monkeypatch.setenv("TRUST_INGRESS_HEADERS", "true")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("HA_TOKEN", "")
    monkeypatch.setenv("HA_BASE_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("SELF_UPDATE_ENABLED", raising=False)

    from app.config import get_settings

    get_settings.cache_clear()

    app = FastAPI()
    app.state.orchestrator = orch
    resolver = AsyncMock()
    resolver.is_admin = AsyncMock(side_effect=lambda uid: uid == "admin-1")
    app.state.admin_resolver = resolver
    app.add_middleware(AuthGateMiddleware)
    app.add_middleware(UserContextMiddleware)
    app.include_router(system_update_router)
    return TestClient(app)


def test_viewer_cannot_check_updates(update_client):
    res = update_client.get(
        "/api/system/update",
        headers={"X-Remote-User-Id": "viewer-1"},
    )
    assert res.status_code == 403


@patch("app.api.system_update._fetch_latest_release", new_callable=AsyncMock)
def test_get_update_info_newer_release(mock_fetch, update_client):
    mock_fetch.return_value = {
        "tag_name": "v9.9.9",
        "body": "## Highlights\n- New feature",
        "html_url": "https://github.com/oraad/solar-ai-optimizer/releases/tag/v9.9.9",
        "published_at": "2026-06-21T12:00:00Z",
    }
    res = update_client.get(
        "/api/system/update",
        headers={"X-Remote-User-Id": "admin-1"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["current_version"] == __version__
    assert data["latest_version"] == "9.9.9"
    assert data["update_available"] is True
    assert "New feature" in data["release_notes"]
    assert data["can_apply"] is False
    assert data["apply_instructions"]


@patch("app.api.system_update._fetch_latest_release", new_callable=AsyncMock)
def test_get_update_info_up_to_date(mock_fetch, update_client):
    mock_fetch.return_value = {
        "tag_name": f"v{__version__}",
        "body": "Current",
        "html_url": "https://example.com",
        "published_at": "2026-06-21T12:00:00Z",
    }
    res = update_client.get(
        "/api/system/update",
        headers={"X-Remote-User-Id": "admin-1"},
    )
    data = res.json()
    assert data["update_available"] is False


@patch("app.api.system_update._spawn_updater")
@patch("app.api.system_update._fetch_latest_release", new_callable=AsyncMock)
@patch("app.api.system_update._docker_socket_available", return_value=True)
def test_post_update_accepted(mock_socket, mock_fetch, mock_spawn, update_client, monkeypatch):
    monkeypatch.setenv("SELF_UPDATE_ENABLED", "true")
    from app.config import get_settings

    get_settings.cache_clear()

    mock_fetch.return_value = {
        "tag_name": "v9.9.9",
        "body": "notes",
        "html_url": "https://example.com",
        "published_at": "2026-06-21T12:00:00Z",
    }
    res = update_client.post(
        "/api/system/update",
        headers={"X-Remote-User-Id": "admin-1"},
    )
    assert res.status_code == 202
    mock_spawn.assert_called_once()


def test_post_update_rejected_when_disabled(update_client):
    res = update_client.post(
        "/api/system/update",
        headers={"X-Remote-User-Id": "admin-1"},
    )
    assert res.status_code == 403
