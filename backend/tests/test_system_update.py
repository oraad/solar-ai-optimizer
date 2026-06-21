"""GET/POST /api/system/update — release checks and self-update gates."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import __version__
from app.api.auth import AuthGateMiddleware, UserContextMiddleware
from app.api.system_update import (
    _is_newer,
    _parse_version,
    router as system_update_router,
)
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
    mock_fetch.return_value = (
        {
            "tag_name": "v9.9.9",
            "body": "## Highlights\n- New feature",
            "html_url": "https://github.com/oraad/solar-ai-optimizer/releases/tag/v9.9.9",
            "published_at": "2026-06-21T12:00:00Z",
        },
        False,
    )
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
    mock_fetch.return_value = (
        {
            "tag_name": f"v{__version__}",
            "body": "Current",
            "html_url": "https://example.com",
            "published_at": "2026-06-21T12:00:00Z",
        },
        False,
    )
    res = update_client.get(
        "/api/system/update",
        headers={"X-Remote-User-Id": "admin-1"},
    )
    data = res.json()
    assert data["update_available"] is False


@patch("app.api.system_update._spawn_updater")
@patch("app.api.system_update._fetch_latest_release", new_callable=AsyncMock)
@patch("app.api.system_update._docker_cli_available", return_value=True)
@patch("app.api.system_update._docker_socket_available", return_value=True)
def test_post_update_accepted(
    mock_socket, mock_cli, mock_fetch, mock_spawn, update_client, monkeypatch
):
    monkeypatch.setenv("SELF_UPDATE_ENABLED", "true")
    from app.config import get_settings

    get_settings.cache_clear()

    mock_fetch.return_value = (
        {
            "tag_name": "v9.9.9",
            "body": "notes",
            "html_url": "https://example.com",
            "published_at": "2026-06-21T12:00:00Z",
        },
        False,
    )
    res = update_client.post(
        "/api/system/update",
        headers={"X-Remote-User-Id": "admin-1"},
    )
    assert res.status_code == 202
    mock_spawn.assert_called_once()
    mock_fetch.assert_called_once()
    assert mock_fetch.call_args.kwargs.get("force") is True


def test_post_update_rejected_when_disabled(update_client):
    res = update_client.post(
        "/api/system/update",
        headers={"X-Remote-User-Id": "admin-1"},
    )
    assert res.status_code == 403


@patch("app.api.system_update._fetch_latest_release", new_callable=AsyncMock)
@patch("app.api.system_update._docker_cli_available", return_value=False)
@patch("app.api.system_update._docker_socket_available", return_value=True)
def test_get_update_info_socket_without_cli(
    mock_socket, mock_cli, mock_fetch, update_client, monkeypatch
):
    monkeypatch.setenv("SELF_UPDATE_ENABLED", "true")
    from app.config import get_settings

    get_settings.cache_clear()

    mock_fetch.return_value = (
        {
            "tag_name": "v9.9.9",
            "body": "notes",
            "html_url": "https://example.com",
            "published_at": "2026-06-21T12:00:00Z",
        },
        False,
    )
    res = update_client.get(
        "/api/system/update",
        headers={"X-Remote-User-Id": "admin-1"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["can_apply"] is False
    assert data["deployment"] == "docker"
    assert "Docker CLI" in data["apply_instructions"]
    assert "v0.5.2+" in data["apply_instructions"]


@patch("app.api.system_update._spawn_updater")
@patch("app.api.system_update._fetch_latest_release", new_callable=AsyncMock)
@patch("app.api.system_update._docker_cli_available", return_value=False)
@patch("app.api.system_update._docker_socket_available", return_value=True)
def test_post_update_rejected_without_docker_cli(
    mock_socket, mock_cli, mock_fetch, mock_spawn, update_client, monkeypatch
):
    monkeypatch.setenv("SELF_UPDATE_ENABLED", "true")
    from app.config import get_settings

    get_settings.cache_clear()

    mock_fetch.return_value = (
        {
            "tag_name": "v9.9.9",
            "body": "notes",
            "html_url": "https://example.com",
            "published_at": "2026-06-21T12:00:00Z",
        },
        False,
    )
    res = update_client.post(
        "/api/system/update",
        headers={"X-Remote-User-Id": "admin-1"},
    )
    assert res.status_code == 503
    assert "Docker CLI" in res.json()["detail"]
    mock_spawn.assert_not_called()


@pytest.mark.parametrize(
    ("latest", "current", "expected"),
    [
        ("0.5.3", "0.5.2", True),
        ("v0.5.3", "0.5.2", True),
        ("0.5.2", "0.5.3", False),
        ("0.5.2", "0.5.2", False),
        ("0.6.0-beta", "0.5.9", True),
        ("1.0.0", "0.9.9", True),
    ],
)
def test_is_newer(latest, current, expected):
    assert _is_newer(latest, current) is expected


@pytest.mark.parametrize(
    ("version", "expected"),
    [
        ("v0.5.3", (0, 5, 3)),
        ("V0.5.3", (0, 5, 3)),
        ("1", (1, 0, 0)),
        ("1.2", (1, 2, 0)),
        ("invalid", (0, 0, 0)),
    ],
)
def test_parse_version(version, expected):
    assert _parse_version(version) == expected


@patch("app.api.system_update._fetch_latest_release", new_callable=AsyncMock)
def test_get_update_info_refresh_forces_fetch(mock_fetch, update_client):
    mock_fetch.return_value = (
        {
            "tag_name": "v9.9.9",
            "body": "notes",
            "html_url": "https://example.com",
            "published_at": "2026-06-21T12:00:00Z",
        },
        False,
    )
    headers = {"X-Remote-User-Id": "admin-1"}

    update_client.get("/api/system/update", headers=headers)
    update_client.get("/api/system/update", params={"refresh": "true"}, headers=headers)

    assert mock_fetch.call_count == 2
    assert mock_fetch.call_args_list[0].kwargs.get("force") is False
    assert mock_fetch.call_args_list[1].kwargs.get("force") is True
