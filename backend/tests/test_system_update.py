"""GET/POST /api/system/update — release checks and self-update gates."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import __version__
from app.api.auth import AuthGateMiddleware, UserContextMiddleware
from app.api.system_update import (
    BACKUP_DIR,
    UPDATE_FAILED_FILE,
    UPDATE_LOCK_FILE,
    UPDATE_LOCK_MAX_AGE_SECONDS,
    UPDATE_PROGRESS_FILE,
    _clear_stale_lock,
    _clear_update_progress,
    _is_newer,
    _is_proxmox_deployment,
    _load_update_progress,
    _parse_backup_filename,
    _parse_version,
    _resolve_image,
    _resolve_restore_image,
    _write_update_progress,
    router as system_update_router,
)
from app.models import SystemStatus, utcnow

SAMPLE_RELEASES = [
    {
        "tag_name": "v9.9.9",
        "body": "## Highlights\n- New feature",
        "html_url": "https://github.com/oraad/solar-ai-optimizer/releases/tag/v9.9.9",
        "published_at": "2026-06-21T12:00:00Z",
        "prerelease": False,
        "draft": False,
    },
    {
        "tag_name": "v0.5.5",
        "body": "Stable",
        "html_url": "https://example.com/v0.5.5",
        "published_at": "2026-06-01T12:00:00Z",
        "prerelease": False,
        "draft": False,
    },
    {
        "tag_name": "v0.5.4",
        "body": "Older",
        "html_url": "https://example.com/v0.5.4",
        "published_at": "2026-05-01T12:00:00Z",
        "prerelease": False,
        "draft": False,
    },
    {
        "tag_name": "v0.5.3-beta",
        "body": "Beta",
        "html_url": "https://example.com/beta",
        "published_at": "2026-04-01T12:00:00Z",
        "prerelease": True,
        "draft": False,
    },
]


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


def _mock_release_fetches(mock_latest, mock_list):
    mock_latest.return_value = (SAMPLE_RELEASES[0], False)
    mock_list.return_value = (SAMPLE_RELEASES, False)


def test_viewer_cannot_check_updates(update_client):
    res = update_client.get(
        "/api/system/update",
        headers={"X-Remote-User-Id": "viewer-1"},
    )
    assert res.status_code == 403


@patch("app.api.system_update._fetch_releases", new_callable=AsyncMock)
@patch("app.api.system_update._fetch_latest_release", new_callable=AsyncMock)
def test_get_update_info_newer_release(mock_fetch, mock_list, update_client):
    _mock_release_fetches(mock_fetch, mock_list)
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
    assert len(data["releases"]) == 3
    assert all(r["version"] != "0.5.3-beta" for r in data["releases"])
    assert data["min_self_update_version"] == "0.5.5"
    assert data["downgrade_warning"]


@patch("app.api.system_update._fetch_releases", new_callable=AsyncMock)
@patch("app.api.system_update._fetch_latest_release", new_callable=AsyncMock)
def test_get_update_info_up_to_date(mock_fetch, mock_list, update_client):
    mock_fetch.return_value = (
        {
            "tag_name": f"v{__version__}",
            "body": "Current",
            "html_url": "https://example.com",
            "published_at": "2026-06-21T12:00:00Z",
        },
        False,
    )
    mock_list.return_value = (
        [
            {
                "tag_name": f"v{__version__}",
                "body": "Current",
                "html_url": "https://example.com",
                "published_at": "2026-06-21T12:00:00Z",
                "prerelease": False,
                "draft": False,
            }
        ],
        False,
    )
    res = update_client.get(
        "/api/system/update",
        headers={"X-Remote-User-Id": "admin-1"},
    )
    data = res.json()
    assert data["update_available"] is False
    assert data["releases"][0]["relation"] == "current"


@patch("app.api.system_update._spawn_updater")
@patch("app.api.system_update._fetch_releases", new_callable=AsyncMock)
@patch("app.api.system_update._fetch_latest_release", new_callable=AsyncMock)
@patch("app.api.system_update._docker_cli_available", return_value=True)
@patch("app.api.system_update._docker_socket_available", return_value=True)
def test_post_update_accepted_latest(
    mock_socket, mock_cli, mock_fetch, mock_list, mock_spawn, update_client, monkeypatch
):
    monkeypatch.setenv("SELF_UPDATE_ENABLED", "true")
    from app.config import get_settings

    get_settings.cache_clear()
    _mock_release_fetches(mock_fetch, mock_list)

    res = update_client.post(
        "/api/system/update",
        headers={"X-Remote-User-Id": "admin-1"},
    )
    assert res.status_code == 202
    body = res.json()
    assert body["target_version"] == "9.9.9"
    mock_spawn.assert_called_once()
    mock_list.assert_called()
    assert mock_list.call_args.kwargs.get("force") is True


@patch("app.api.system_update._spawn_updater")
@patch("app.api.system_update._fetch_releases", new_callable=AsyncMock)
@patch("app.api.system_update._docker_cli_available", return_value=True)
@patch("app.api.system_update._docker_socket_available", return_value=True)
def test_post_update_with_version_downgrade(
    mock_socket, mock_cli, mock_list, mock_spawn, update_client, monkeypatch
):
    monkeypatch.setenv("SELF_UPDATE_ENABLED", "true")
    from app.config import get_settings

    get_settings.cache_clear()
    mock_list.return_value = (SAMPLE_RELEASES, False)

    res = update_client.post(
        "/api/system/update",
        headers={"X-Remote-User-Id": "admin-1"},
        json={"version": "0.5.5"},
    )
    assert res.status_code == 202
    body = res.json()
    assert body["target_version"] == "0.5.5"
    assert body["is_downgrade"] is True
    mock_spawn.assert_called_once()
    kwargs = mock_spawn.call_args.kwargs
    assert kwargs["target_image"].endswith(":0.5.5")


@patch("app.api.system_update._fetch_releases", new_callable=AsyncMock)
@patch("app.api.system_update._docker_cli_available", return_value=True)
@patch("app.api.system_update._docker_socket_available", return_value=True)
def test_post_update_rejects_current_version(
    mock_socket, mock_cli, mock_list, update_client, monkeypatch
):
    monkeypatch.setenv("SELF_UPDATE_ENABLED", "true")
    from app.config import get_settings

    get_settings.cache_clear()
    mock_list.return_value = (
        [
            {
                "tag_name": f"v{__version__}",
                "body": "x",
                "prerelease": False,
                "draft": False,
            }
        ],
        False,
    )
    res = update_client.post(
        "/api/system/update",
        json={"version": __version__},
        headers={"X-Remote-User-Id": "admin-1"},
    )
    assert res.status_code == 400
    assert "Already running" in res.json()["detail"]


@patch("app.api.system_update._fetch_releases", new_callable=AsyncMock)
@patch("app.api.system_update._docker_cli_available", return_value=True)
@patch("app.api.system_update._docker_socket_available", return_value=True)
def test_post_update_rejects_unknown_version(
    mock_socket, mock_cli, mock_list, update_client, monkeypatch
):
    monkeypatch.setenv("SELF_UPDATE_ENABLED", "true")
    from app.config import get_settings

    get_settings.cache_clear()
    mock_list.return_value = (SAMPLE_RELEASES, False)

    res = update_client.post(
        "/api/system/update",
        json={"version": "0.0.0"},
        headers={"X-Remote-User-Id": "admin-1"},
    )
    assert res.status_code == 400


@patch("app.api.system_update._fetch_releases", new_callable=AsyncMock)
@patch("app.api.system_update._docker_cli_available", return_value=True)
@patch("app.api.system_update._docker_socket_available", return_value=True)
def test_post_update_rejects_below_min_self_update(
    mock_socket, mock_cli, mock_list, update_client, monkeypatch
):
    monkeypatch.setenv("SELF_UPDATE_ENABLED", "true")
    from app.config import get_settings

    get_settings.cache_clear()
    mock_list.return_value = (
        [
            {
                "tag_name": "v0.5.4",
                "body": "old",
                "prerelease": False,
                "draft": False,
            }
        ],
        False,
    )
    res = update_client.post(
        "/api/system/update",
        json={"version": "0.5.4"},
        headers={"X-Remote-User-Id": "admin-1"},
    )
    assert res.status_code == 400
    assert "0.5.5" in res.json()["detail"]


def test_post_update_rejected_when_disabled(update_client):
    res = update_client.post(
        "/api/system/update",
        headers={"X-Remote-User-Id": "admin-1"},
    )
    assert res.status_code == 403


@patch("app.api.system_update._fetch_releases", new_callable=AsyncMock)
@patch("app.api.system_update._fetch_latest_release", new_callable=AsyncMock)
@patch("app.api.system_update._docker_cli_available", return_value=False)
@patch("app.api.system_update._docker_socket_available", return_value=True)
def test_get_update_info_socket_without_cli(
    mock_socket, mock_cli, mock_fetch, mock_list, update_client, monkeypatch
):
    monkeypatch.setenv("SELF_UPDATE_ENABLED", "true")
    from app.config import get_settings

    get_settings.cache_clear()
    _mock_release_fetches(mock_fetch, mock_list)

    res = update_client.get(
        "/api/system/update",
        headers={"X-Remote-User-Id": "admin-1"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["can_apply"] is False
    assert data["deployment"] == "docker"
    assert "Docker CLI" in data["apply_instructions"]
    assert "v0.5.5+" in data["apply_instructions"]


@patch("app.api.system_update._spawn_updater")
@patch("app.api.system_update._fetch_releases", new_callable=AsyncMock)
@patch("app.api.system_update._docker_cli_available", return_value=False)
@patch("app.api.system_update._docker_socket_available", return_value=True)
def test_post_update_rejected_without_docker_cli(
    mock_socket, mock_cli, mock_list, mock_spawn, update_client, monkeypatch
):
    monkeypatch.setenv("SELF_UPDATE_ENABLED", "true")
    from app.config import get_settings

    get_settings.cache_clear()
    mock_list.return_value = (SAMPLE_RELEASES, False)

    res = update_client.post(
        "/api/system/update",
        headers={"X-Remote-User-Id": "admin-1"},
    )
    assert res.status_code == 503
    assert "Docker CLI" in res.json()["detail"]
    mock_spawn.assert_not_called()


@patch("app.api.system_update._spawn_restore")
@patch("app.api.system_update._docker_cli_available", return_value=True)
@patch("app.api.system_update._docker_socket_available", return_value=True)
def test_post_restore_accepted(
    mock_socket, mock_cli, mock_restore, update_client, monkeypatch, tmp_path
):
    monkeypatch.setenv("SELF_UPDATE_ENABLED", "true")
    from app.config import get_settings

    get_settings.cache_clear()
    backup_dir = tmp_path / BACKUP_DIR
    backup_dir.mkdir()
    (backup_dir / "pre-0.5.5-1.tar.gz").write_bytes(b"x" * 10)
    (tmp_path / ".deploy_state.json").write_text(
        json.dumps({"previous_image": "ghcr.io/oraad/solar-ai-optimizer:0.5.5"}),
        encoding="utf-8",
    )

    res = update_client.post(
        "/api/system/update/restore",
        headers={"X-Remote-User-Id": "admin-1"},
    )
    assert res.status_code == 202
    mock_restore.assert_called_once()


def test_viewer_cannot_restore(update_client):
    res = update_client.post(
        "/api/system/update/restore",
        headers={"X-Remote-User-Id": "viewer-1"},
    )
    assert res.status_code == 403


@patch("app.api.system_update._fetch_releases", new_callable=AsyncMock)
@patch("app.api.system_update._fetch_latest_release", new_callable=AsyncMock)
def test_get_lists_backups_and_deploy_state(
    mock_fetch, mock_list, update_client, tmp_path
):
    _mock_release_fetches(mock_fetch, mock_list)
    (tmp_path / ".deploy_state.json").write_text(
        json.dumps({"previous_version": "0.5.6"}),
        encoding="utf-8",
    )
    backup_dir = tmp_path / BACKUP_DIR
    backup_dir.mkdir()
    (backup_dir / "pre-0.5.7-99.tar.gz").write_bytes(b"backup")

    res = update_client.get(
        "/api/system/update",
        headers={"X-Remote-User-Id": "admin-1"},
    )
    data = res.json()
    assert data["previous_version"] == "0.5.6"
    assert len(data["backups"]) == 1
    assert data["backups"][0]["name"] == "pre-0.5.7-99.tar.gz"


def test_resolve_image_replaces_tag():
    assert (
        _resolve_image("ghcr.io/oraad/solar-ai-optimizer:latest", "0.5.6")
        == "ghcr.io/oraad/solar-ai-optimizer:0.5.6"
    )
    assert (
        _resolve_image("ghcr.io/oraad/solar-ai-optimizer:0.5.5", "0.5.6")
        == "ghcr.io/oraad/solar-ai-optimizer:0.5.6"
    )


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


@patch("app.api.system_update._fetch_releases", new_callable=AsyncMock)
@patch("app.api.system_update._fetch_latest_release", new_callable=AsyncMock)
def test_get_update_info_refresh_forces_fetch(mock_fetch, mock_list, update_client):
    _mock_release_fetches(mock_fetch, mock_list)
    headers = {"X-Remote-User-Id": "admin-1"}

    update_client.get("/api/system/update", headers=headers)
    update_client.get("/api/system/update", params={"refresh": "true"}, headers=headers)

    assert mock_fetch.call_count == 2
    assert mock_fetch.call_args_list[0].kwargs.get("force") is False
    assert mock_fetch.call_args_list[1].kwargs.get("force") is True
    assert mock_list.call_count == 2


def test_parse_backup_filename_new_format():
    meta = _parse_backup_filename("pre-from-0.5.7-to-0.5.8-1710000000.tar.gz")
    assert meta == {"before_version": "0.5.7", "target_version": "0.5.8"}


def test_parse_backup_filename_legacy():
    meta = _parse_backup_filename("pre-0.5.7-99.tar.gz")
    assert meta == {"before_version": None, "target_version": "0.5.7"}


def test_resolve_restore_image_prefers_from_version(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.config import get_settings

    get_settings.cache_clear()
    settings = get_settings()
    deploy_state = {
        "previous_image": "ghcr.io/oraad/solar-ai-optimizer:0.5.6",
        "image": "ghcr.io/oraad/solar-ai-optimizer:0.5.6",
    }
    pending = {
        "from_version": "0.5.7",
        "target_image": "ghcr.io/oraad/solar-ai-optimizer:0.5.8",
    }
    image = _resolve_restore_image(settings, deploy_state, pending)
    assert image == "ghcr.io/oraad/solar-ai-optimizer:0.5.7"


def test_resolve_restore_image_falls_back_to_deploy_state_image(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.config import get_settings

    get_settings.cache_clear()
    settings = get_settings()
    deploy_state = {"image": "ghcr.io/oraad/solar-ai-optimizer:0.5.5"}
    pending = {"target_image": "ghcr.io/oraad/solar-ai-optimizer:0.5.8"}
    image = _resolve_restore_image(settings, deploy_state, pending)
    assert image == "ghcr.io/oraad/solar-ai-optimizer:0.5.5"


def test_clear_stale_lock_removes_old_lock(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.config import get_settings

    get_settings.cache_clear()
    settings = get_settings()
    lock = tmp_path / UPDATE_LOCK_FILE
    lock.write_text("")
    old = time.time() - UPDATE_LOCK_MAX_AGE_SECONDS - 60
    os.utime(lock, (old, old))
    failed_path = tmp_path / UPDATE_FAILED_FILE
    failed_path.write_text(json.dumps({"message": "failed", "backup": "pre-x.tar.gz"}))
    _clear_stale_lock(settings)
    assert not lock.exists()
    assert failed_path.is_file()


def test_clear_stale_lock_clears_lock_when_failed_present(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.config import get_settings

    get_settings.cache_clear()
    settings = get_settings()
    lock = tmp_path / UPDATE_LOCK_FILE
    lock.write_text("")
    failed_path = tmp_path / UPDATE_FAILED_FILE
    failed_path.write_text(json.dumps({"message": "failed"}))
    _clear_stale_lock(settings)
    assert not lock.exists()
    assert failed_path.is_file()


@patch("app.api.system_update._fetch_releases", new_callable=AsyncMock)
@patch("app.api.system_update._fetch_latest_release", new_callable=AsyncMock)
def test_get_returns_update_failed(mock_fetch, mock_list, update_client, tmp_path):
    _mock_release_fetches(mock_fetch, mock_list)
    (tmp_path / UPDATE_FAILED_FILE).write_text(
        json.dumps(
            {
                "message": "image pull failed",
                "backup": ".update-backups/pre-from-0.5.7-to-0.5.8-1.tar.gz",
            }
        ),
        encoding="utf-8",
    )
    res = update_client.get(
        "/api/system/update",
        headers={"X-Remote-User-Id": "admin-1"},
    )
    data = res.json()
    assert data["update_failed"]["message"] == "image pull failed"
    assert "pre-from-0.5.7-to-0.5.8" in data["update_failed"]["backup"]


@patch("app.api.system_update._fetch_releases", new_callable=AsyncMock)
@patch("app.api.system_update._fetch_latest_release", new_callable=AsyncMock)
def test_get_lists_backups_new_filename_format(
    mock_fetch, mock_list, update_client, tmp_path
):
    _mock_release_fetches(mock_fetch, mock_list)
    backup_dir = tmp_path / BACKUP_DIR
    backup_dir.mkdir()
    (backup_dir / "pre-from-0.5.6-to-0.5.7-100.tar.gz").write_bytes(b"backup")

    res = update_client.get(
        "/api/system/update",
        headers={"X-Remote-User-Id": "admin-1"},
    )
    data = res.json()
    assert len(data["backups"]) == 1
    assert data["backups"][0]["name"] == "pre-from-0.5.6-to-0.5.7-100.tar.gz"
    assert data["backups"][0]["before_version"] == "0.5.6"


def test_is_proxmox_deployment(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SELF_UPDATE_ENV_FILE", "/opt/solar-ai-optimizer/solar.env")
    from app.config import get_settings

    get_settings.cache_clear()
    settings = get_settings()
    assert _is_proxmox_deployment(settings) is True


def test_load_update_progress_requires_lock(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.config import get_settings

    get_settings.cache_clear()
    settings = get_settings()
    _write_update_progress(
        settings,
        {
            "operation": "update",
            "stage": "pulling",
            "message": "Pulling image",
            "from_version": "0.5.7",
            "to_version": "0.5.8",
        },
    )
    assert _load_update_progress(settings) is None


@patch("app.api.system_update._fetch_releases", new_callable=AsyncMock)
@patch("app.api.system_update._fetch_latest_release", new_callable=AsyncMock)
def test_get_returns_update_progress_when_locked(
    mock_fetch, mock_list, update_client, tmp_path
):
    _mock_release_fetches(mock_fetch, mock_list)
    (tmp_path / UPDATE_LOCK_FILE).write_text("123", encoding="utf-8")
    (tmp_path / UPDATE_PROGRESS_FILE).write_text(
        json.dumps(
            {
                "operation": "update",
                "stage": "pulling",
                "message": "Pulling ghcr.io/oraad/solar-ai-optimizer:0.5.8",
                "from_version": "0.5.7",
                "to_version": "0.5.8",
            }
        ),
        encoding="utf-8",
    )
    res = update_client.get(
        "/api/system/update",
        headers={"X-Remote-User-Id": "admin-1"},
    )
    data = res.json()
    assert data["update_progress"]["stage"] == "pulling"
    assert data["update_in_progress"] is True


@patch("app.api.system_update._fetch_releases", new_callable=AsyncMock)
@patch("app.api.system_update._fetch_latest_release", new_callable=AsyncMock)
@patch("app.api.system_update._docker_cli_available", return_value=True)
@patch("app.api.system_update._docker_socket_available", return_value=True)
def test_get_proxmox_deployment_kind(
    mock_socket, mock_cli, mock_fetch, mock_list, update_client, monkeypatch
):
    monkeypatch.setenv("SELF_UPDATE_ENABLED", "true")
    monkeypatch.setenv("SELF_UPDATE_ENV_FILE", "/opt/solar-ai-optimizer/solar.env")
    from app.config import get_settings

    get_settings.cache_clear()
    _mock_release_fetches(mock_fetch, mock_list)

    res = update_client.get(
        "/api/system/update",
        headers={"X-Remote-User-Id": "admin-1"},
    )
    assert res.json()["deployment"] == "proxmox"


def test_clear_stale_lock_clears_progress(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.config import get_settings

    get_settings.cache_clear()
    settings = get_settings()
    lock = tmp_path / UPDATE_LOCK_FILE
    lock.write_text("")
    old = time.time() - UPDATE_LOCK_MAX_AGE_SECONDS - 60
    os.utime(lock, (old, old))
    progress = tmp_path / UPDATE_PROGRESS_FILE
    progress.write_text('{"stage":"pulling"}', encoding="utf-8")
    _clear_stale_lock(settings)
    assert not lock.exists()
    assert not progress.exists()
    _clear_update_progress(settings)
