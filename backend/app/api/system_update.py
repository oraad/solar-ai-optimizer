"""Software update checks (GitHub releases) and opt-in Docker self-update."""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel

from .. import __version__
from ..i18n import api_error, t
from ..i18n.serialize import localize_payload
from ..config import Settings, get_settings
from .session import SessionUser, require_admin

log = logging.getLogger("api.system_update")

router = APIRouter(prefix="/api/system", tags=["system"])

GITHUB_RELEASES_LATEST = (
    "https://api.github.com/repos/oraad/solar-ai-optimizer/releases/latest"
)
GITHUB_RELEASES_LIST = (
    "https://api.github.com/repos/oraad/solar-ai-optimizer/releases?per_page=20"
)
DOCKER_SOCKET = Path("/var/run/docker.sock")
UPDATE_LOCK_FILE = ".update_in_progress"
UPDATE_PENDING_FILE = ".update_pending.json"
UPDATE_FAILED_FILE = ".update_failed.json"
UPDATE_PROGRESS_FILE = ".update_progress.json"
DEPLOY_STATE_FILE = ".deploy_state.json"
PROXMOX_ENV_PREFIX = "/opt/solar-ai-optimizer"
BACKUP_DIR = ".update-backups"
BACKUP_RETENTION = 3
UPDATE_LOCK_MAX_AGE_SECONDS = 30 * 60
MIN_SELF_UPDATE_VERSION = "0.5.10"
UPDATE_SCRIPT = "/app/scripts/docker-self-update.sh"
RELEASES_LIST_LIMIT = 20

RELEASE_CACHE_TTL_SECONDS = 15 * 60

_release_cache: dict[str, Any] | None = None
_release_cache_at: float = 0.0
_releases_list_cache: list[dict[str, Any]] | None = None
_releases_list_cache_at: float = 0.0
_release_checked_at: datetime | None = None

DeploymentKind = Literal["addon", "docker", "compose", "proxmox", "unknown"]
ReleaseRelation = Literal["current", "newer", "older"]


class ApplyUpdateRequest(BaseModel):
    version: str | None = None


class RestoreBackupRequest(BaseModel):
    backup: str | None = None


def _parse_version(version: str) -> tuple[int, int, int]:
    cleaned = version.lstrip("vV").strip()
    match = re.match(r"^(\d+)(?:\.(\d+))?(?:\.(\d+))?", cleaned)
    if not match:
        return (0, 0, 0)
    return tuple(int(part or 0) for part in match.groups())


def _normalize_version(tag: str) -> str | None:
    cleaned = str(tag).lstrip("vV").strip()
    if not re.match(r"^\d+\.\d+\.\d+$", cleaned):
        return None
    return cleaned


def _is_newer(latest: str, current: str) -> bool:
    return _parse_version(latest) > _parse_version(current)


def _version_relation(version: str, current: str) -> ReleaseRelation:
    if _parse_version(version) == _parse_version(current):
        return "current"
    if _is_newer(version, current):
        return "newer"
    return "older"


def _version_below_min(version: str) -> bool:
    return _parse_version(version) < _parse_version(MIN_SELF_UPDATE_VERSION)


def _resolve_image(base_image: str, version: str) -> str:
    if ":" in base_image.rsplit("/", 1)[-1]:
        base, _ = base_image.rsplit(":", 1)
    else:
        base = base_image
    return f"{base}:{version}"


def _docker_socket_available() -> bool:
    try:
        return DOCKER_SOCKET.is_socket()
    except OSError:
        return False


def _docker_cli_available() -> bool:
    return shutil.which("docker") is not None


def _is_proxmox_deployment(settings: Settings) -> bool:
    return settings.self_update_env_file.strip().startswith(PROXMOX_ENV_PREFIX)


def _detect_deployment(settings: Settings) -> DeploymentKind:
    if settings.is_addon:
        return "addon"
    if settings.self_update_enabled and _docker_socket_available():
        if _is_proxmox_deployment(settings):
            return "proxmox"
        return "docker"
    if Path("/app/run.sh").is_file() and not settings.self_update_enabled:
        return "compose"
    return "unknown"


def _can_apply(settings: Settings) -> bool:
    return (
        settings.self_update_enabled
        and _docker_socket_available()
        and _docker_cli_available()
        and not settings.is_addon
    )


def _apply_instructions(
    settings: Settings,
    deployment: DeploymentKind,
    version: str | None = None,
) -> str | None:
    tag = version or "latest"
    image = _resolve_image(settings.self_update_image, tag) if version else (
        settings.self_update_image
    )
    if deployment == "addon":
        return t("api.update.instructions.addon")
    if deployment in ("docker", "proxmox"):
        if not _docker_cli_available():
            return t(
                "api.update.docker_cli_missing",
                {"min_version": MIN_SELF_UPDATE_VERSION},
            )
        return None
    if deployment == "compose":
        if version:
            return t(
                "api.update.instructions.compose_versioned",
                {"image": image},
            )
        return t("api.update.instructions.compose")
    if version:
        return t("api.update.instructions.proxmox_versioned", {"image": image})
    return t("api.update.instructions.proxmox")


def _data_dir(settings: Settings) -> Path:
    return Path(settings.data_dir)


def _read_json_file(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _image_version(image: str) -> str | None:
    tag = image.rsplit(":", 1)[-1] if ":" in image.rsplit("/", 1)[-1] else None
    if not tag:
        return None
    return _normalize_version(tag)


def _parse_backup_filename(name: str) -> dict[str, str | None]:
    """Parse backup metadata from filename."""
    m = re.match(
        r"^pre-from-(\d+\.\d+\.\d+)-to-(\d+\.\d+\.\d+)-(\d+)\.tar\.gz$",
        name,
    )
    if m:
        return {
            "before_version": m.group(1),
            "target_version": m.group(2),
        }
    m = re.match(r"^pre-(\d+\.\d+\.\d+)-(\d+)\.tar\.gz$", name)
    if m:
        return {"before_version": None, "target_version": m.group(1)}
    return {"before_version": None, "target_version": None}


def _resolve_restore_image(
    settings: Settings,
    deploy_state: dict[str, Any],
    pending: dict[str, Any],
) -> str:
    from_version = pending.get("from_version")
    if from_version:
        normalized = _normalize_version(str(from_version))
        if normalized:
            return _resolve_image(settings.self_update_image, normalized)
    image = deploy_state.get("image")
    if image:
        return str(image)
    return settings.self_update_image


def _load_update_failed(settings: Settings) -> dict[str, Any] | None:
    path = _data_dir(settings) / UPDATE_FAILED_FILE
    if not path.is_file():
        return None
    try:
        raw = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not raw:
        return None
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    return {"message": raw, "backup": None}


def _clear_update_failed(settings: Settings) -> None:
    (_data_dir(settings) / UPDATE_FAILED_FILE).unlink(missing_ok=True)


def _load_deploy_state(settings: Settings) -> dict[str, Any] | None:
    return _read_json_file(_data_dir(settings) / DEPLOY_STATE_FILE)


def _list_backups(settings: Settings) -> list[dict[str, Any]]:
    backup_root = _data_dir(settings) / BACKUP_DIR
    if not backup_root.is_dir():
        return []
    entries: list[dict[str, Any]] = []
    for path in sorted(backup_root.glob("*.tar.gz"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            stat = path.stat()
        except OSError:
            continue
        name = path.name
        meta = _parse_backup_filename(name)
        before_version = meta.get("before_version") or meta.get("target_version")
        entries.append(
            {
                "name": name,
                "created_at": datetime.fromtimestamp(stat.st_mtime, UTC).isoformat().replace(
                    "+00:00", "Z"
                ),
                "size_bytes": stat.st_size,
                "before_version": before_version,
            }
        )
    return entries


def _clear_update_progress(settings: Settings) -> None:
    (_data_dir(settings) / UPDATE_PROGRESS_FILE).unlink(missing_ok=True)


def _write_update_progress(settings: Settings, payload: dict[str, Any]) -> None:
    data_dir = _data_dir(settings)
    data_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    body = dict(payload)
    body.setdefault("started_at", now)
    body["updated_at"] = now
    (data_dir / UPDATE_PROGRESS_FILE).write_text(
        json.dumps(body, indent=2),
        encoding="utf-8",
    )


def _load_update_progress(settings: Settings) -> dict[str, Any] | None:
    if not _update_in_progress(settings):
        return None
    data = _read_json_file(_data_dir(settings) / UPDATE_PROGRESS_FILE)
    if not data or not isinstance(data.get("stage"), str):
        return None
    return data


def _clear_stale_lock(settings: Settings) -> None:
    lock = _lock_path(settings)
    if not lock.exists():
        return
    failed = _load_update_failed(settings)
    if failed is not None:
        lock.unlink(missing_ok=True)
        _clear_update_progress(settings)
        return
    try:
        age = time.time() - lock.stat().st_mtime
    except OSError:
        return
    if age > UPDATE_LOCK_MAX_AGE_SECONDS:
        log.warning(
            "Clearing stale update lock (age %.0fs > %ss)",
            age,
            UPDATE_LOCK_MAX_AGE_SECONDS,
        )
        lock.unlink(missing_ok=True)
        _clear_update_progress(settings)


async def _fetch_latest_release(*, force: bool = False) -> tuple[dict[str, Any] | None, bool]:
    """Return (release_data, from_cache)."""
    global _release_cache, _release_cache_at, _release_checked_at

    now = time.monotonic()
    if (
        not force
        and _release_cache is not None
        and now - _release_cache_at < RELEASE_CACHE_TTL_SECONDS
    ):
        return _release_cache, True

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                GITHUB_RELEASES_LATEST,
                headers={"Accept": "application/vnd.github+json"},
            )
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPError as exc:
        log.warning("Failed to fetch GitHub release: %s", exc)
        return _release_cache, _release_cache is not None

    _release_cache = data
    _release_cache_at = now
    _release_checked_at = datetime.now(UTC)
    return data, False


async def _fetch_releases(*, force: bool = False) -> tuple[list[dict[str, Any]], bool]:
    """Return (stable_releases, from_cache)."""
    global _releases_list_cache, _releases_list_cache_at, _release_checked_at

    now = time.monotonic()
    if (
        not force
        and _releases_list_cache is not None
        and now - _releases_list_cache_at < RELEASE_CACHE_TTL_SECONDS
    ):
        return _releases_list_cache, True

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                GITHUB_RELEASES_LIST,
                headers={"Accept": "application/vnd.github+json"},
            )
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPError as exc:
        log.warning("Failed to fetch GitHub releases list: %s", exc)
        if _releases_list_cache is not None:
            return _releases_list_cache, True
        return [], False

    if not isinstance(data, list):
        return _releases_list_cache or [], _releases_list_cache is not None

    stable = [
        r
        for r in data
        if isinstance(r, dict)
        and not r.get("draft")
        and not r.get("prerelease")
        and _normalize_version(str(r.get("tag_name", "")))
    ][:RELEASES_LIST_LIMIT]

    _releases_list_cache = stable
    _releases_list_cache_at = now
    _release_checked_at = datetime.now(UTC)
    return stable, False


def _build_release_summaries(
    releases: list[dict[str, Any]],
    current: str,
    settings: Settings,
    can_apply: bool,
    deployment: DeploymentKind,
) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for release in releases:
        version = _normalize_version(str(release.get("tag_name", "")))
        if not version:
            continue
        relation = _version_relation(version, current)
        installable = (
            can_apply
            and relation != "current"
            and not _version_below_min(version)
        )
        summary: dict[str, Any] = {
            "version": version,
            "tag_name": str(release.get("tag_name", "")),
            "published_at": release.get("published_at"),
            "release_url": release.get("html_url"),
            "release_notes": release.get("body") or None,
            "relation": relation,
            "installable": installable,
            "image": _resolve_image(settings.self_update_image, version),
        }
        if not can_apply and deployment != "addon":
            summary["apply_instructions"] = _apply_instructions(
                settings, deployment, version
            )
        summaries.append(summary)
    return summaries


def _lock_path(settings: Settings) -> Path:
    return _data_dir(settings) / UPDATE_LOCK_FILE


def _update_in_progress(settings: Settings) -> bool:
    return _lock_path(settings).exists()


def _set_update_lock(settings: Settings) -> None:
    _data_dir(settings).mkdir(parents=True, exist_ok=True)
    _lock_path(settings).write_text(str(time.time()), encoding="utf-8")


def _write_update_pending(
    settings: Settings,
    *,
    from_version: str,
    to_version: str,
    target_image: str,
    is_downgrade: bool,
) -> None:
    payload = {
        "from_version": from_version,
        "to_version": to_version,
        "target_image": target_image,
        "is_downgrade": is_downgrade,
    }
    path = _data_dir(settings) / UPDATE_PENDING_FILE
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _current_container_image(settings: Settings) -> str | None:
    """Image ref of the running app container (for restore helper spawn)."""
    container = settings.self_update_container
    try:
        result = subprocess.run(
            ["docker", "inspect", "-f", "{{.Config.Image}}", container],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    image = result.stdout.strip()
    return image or None


def _helper_env(settings: Settings, **extra: str) -> list[str]:
    env: list[str] = [
        "-e",
        f"CONTAINER={settings.self_update_container}",
        "-e",
        f"DATA_VOL={settings.self_update_data_volume}",
        "-e",
        f"DATA_PATH={settings.self_update_data_path}",
        "-e",
        f"PORT={settings.self_update_port}",
        "-e",
        f"ENV_FILE={settings.self_update_env_file.strip()}",
        "-e",
        f"HEALTH_TIMEOUT={settings.self_update_health_timeout}",
        "-e",
        f"BACKUP_DIR={BACKUP_DIR}",
        "-e",
        f"BACKUP_RETENTION={BACKUP_RETENTION}",
        "-e",
        f"LOCK_FILE={UPDATE_LOCK_FILE}",
        "-e",
        f"PENDING_FILE={UPDATE_PENDING_FILE}",
        "-e",
        f"FAILED_FILE={UPDATE_FAILED_FILE}",
        "-e",
        f"PROGRESS_FILE={UPDATE_PROGRESS_FILE}",
        "-e",
        f"DEPLOY_STATE={DEPLOY_STATE_FILE}",
    ]
    for key, value in extra.items():
        env.extend(["-e", f"{key}={value}"])
    return env


def _build_helper_argv(
    settings: Settings,
    *,
    operation: Literal["update", "restore"],
    helper_image: str,
    target_image: str,
    from_version: str,
    to_version: str,
    backup_name: str = "",
) -> list[str]:
    """docker run argv for the detached self-update helper."""
    cmd: list[str] = [
        "docker",
        "run",
        "-d",
        "--rm",
        "--label",
        "solar.self-update=1",
        "-v",
        f"{DOCKER_SOCKET}:{DOCKER_SOCKET}",
        "-v",
        f"{settings.self_update_data_volume}:{settings.self_update_data_path}",
    ]
    env_file = settings.self_update_env_file.strip()
    if env_file:
        parent = str(Path(env_file).parent)
        cmd.extend(["-v", f"{parent}:{parent}:ro"])
    cmd.extend(_helper_env(
        settings,
        TARGET_IMAGE=target_image,
        FROM_VERSION=from_version,
        TO_VERSION=to_version,
        BACKUP_NAME=backup_name,
    ))
    cmd.extend([
        "--entrypoint",
        UPDATE_SCRIPT,
        helper_image,
        operation,
    ])
    return cmd


def _spawn_helper(
    settings: Settings,
    cmd: list[str],
    *,
    log_label: str,
) -> None:
    log.info("Spawning %s: %s", log_label, " ".join(cmd))
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
        text=True,
    )
    # Brief wait to capture immediate spawn errors / container id
    try:
        stdout, stderr = proc.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        log.info("Helper started in background (pid=%s)", proc.pid)
        return
    if proc.returncode != 0:
        detail = (stderr or stdout or "").strip() or f"exit {proc.returncode}"
        raise OSError(f"Helper failed to start: {detail}")
    container_id = (stdout or "").strip()
    if container_id:
        log.info("Helper container id: %s", container_id[:12])


def _spawn_updater(
    settings: Settings,
    *,
    target_image: str,
    from_version: str,
    to_version: str,
) -> None:
    cmd = _build_helper_argv(
        settings,
        operation="update",
        helper_image=target_image,
        target_image=target_image,
        from_version=from_version,
        to_version=to_version,
    )
    _spawn_helper(
        settings,
        cmd,
        log_label=f"self-update for {target_image}",
    )


def _spawn_restore(
    settings: Settings,
    *,
    backup_name: str,
    restore_image: str,
) -> None:
    restore_version = _image_version(restore_image) or __version__
    helper_image = _current_container_image(settings) or settings.self_update_image
    cmd = _build_helper_argv(
        settings,
        operation="restore",
        helper_image=helper_image,
        target_image=restore_image,
        from_version=restore_version,
        to_version=restore_version,
        backup_name=backup_name,
    )
    _spawn_helper(
        settings,
        cmd,
        log_label=f"restore from {backup_name}",
    )


def _resolve_target_version(
    releases: list[dict[str, Any]],
    requested: str | None,
    current: str,
) -> str:
    summaries = [
        s
        for r in releases
        if (s := _normalize_version(str(r.get("tag_name", ""))))
    ]
    if requested:
        normalized = _normalize_version(requested)
        if not normalized:
            raise api_error("api.update.invalid_version", 400)
        known = {_normalize_version(str(r.get("tag_name", ""))) for r in releases}
        if normalized not in known:
            raise api_error("api.update.unknown_release", 400)
        return normalized
    if not summaries:
        raise api_error("api.update.release_unavailable", 503)
    latest = _normalize_version(str(releases[0].get("tag_name", "")))
    if not latest:
        raise api_error("api.update.release_unavailable", 503)
    return latest


async def build_update_info(
    settings: Settings | None = None,
    *,
    force_release_refresh: bool = False,
) -> dict[str, Any]:
    settings = settings or get_settings()
    _clear_stale_lock(settings)
    current = __version__
    deployment = _detect_deployment(settings)
    can_apply = _can_apply(settings)

    release, release_from_cache = await _fetch_latest_release(force=force_release_refresh)
    releases_raw, _ = await _fetch_releases(force=force_release_refresh)
    release_summaries = _build_release_summaries(
        releases_raw, current, settings, can_apply, deployment
    )

    latest_version: str | None = None
    release_notes: str | None = None
    release_url: str | None = None
    published_at: str | None = None
    update_available = False

    if release:
        tag = str(release.get("tag_name", "")).lstrip("v")
        if tag:
            latest_version = tag
            update_available = _is_newer(tag, current)
        release_notes = release.get("body") or None
        release_url = release.get("html_url") or None
        published_at = release.get("published_at") or None

    deploy_state = _load_deploy_state(settings)
    previous_version = deploy_state.get("previous_version") if deploy_state else None
    update_failed = _load_update_failed(settings)

    release_checked_at = (
        _release_checked_at.isoformat().replace("+00:00", "Z")
        if _release_checked_at is not None
        else None
    )

    progress = _load_update_progress(settings)
    if progress and isinstance(progress.get("message"), str):
        progress_msgs = {
            "Preparing update": "api.update.preparing_update",
            "Preparing restore": "api.update.preparing_restore",
        }
        key = progress_msgs.get(progress["message"])
        if key:
            progress = {**progress, "message": t(key)}

    return localize_payload(
        {
        "current_version": current,
        "latest_version": latest_version,
        "update_available": update_available,
        "release_notes": release_notes,
        "release_url": release_url,
        "published_at": published_at,
        "can_apply": can_apply,
        "deployment": deployment,
        "apply_instructions": _apply_instructions(settings, deployment),
        "update_in_progress": _update_in_progress(settings),
        "update_progress": progress,
        "release_checked_at": release_checked_at,
        "release_from_cache": release_from_cache,
        "releases": release_summaries,
        "previous_version": previous_version,
        "min_self_update_version": MIN_SELF_UPDATE_VERSION,
        "backups": _list_backups(settings),
        "downgrade_warning": t("api.update.downgrade_warning"),
        "update_failed": update_failed,
        }
    )


@router.get("/update")
async def get_update_info(
    _admin: SessionUser = Depends(require_admin),
    refresh: bool = Query(False),
) -> dict[str, Any]:
    return await build_update_info(force_release_refresh=refresh)


@router.post("/update", status_code=202)
async def apply_update(
    body: ApplyUpdateRequest | None = None,
    _admin: SessionUser = Depends(require_admin),
    settings: Settings = Depends(get_settings),
) -> Response:
    if not _can_apply(settings):
        if (
            settings.self_update_enabled
            and not settings.is_addon
            and _docker_socket_available()
            and not _docker_cli_available()
        ):
            raise api_error(
                "api.update.docker_cli_missing",
                503,
                min_version=MIN_SELF_UPDATE_VERSION,
            )
        raise api_error("api.update.self_update_disabled", 403)
    if _update_in_progress(settings):
        raise api_error("api.update.already_in_progress", 409)

    current = __version__
    releases_raw, _ = await _fetch_releases(force=True)
    target_version = _resolve_target_version(
        releases_raw, body.version if body else None, current
    )

    if _parse_version(target_version) == _parse_version(current):
        raise api_error("api.update.already_running_version", 400)
    if _version_below_min(target_version):
        raise api_error(
            "api.update.version_below_minimum",
            400,
            version=target_version,
            min_version=MIN_SELF_UPDATE_VERSION,
        )

    target_image = _resolve_image(settings.self_update_image, target_version)
    is_downgrade = _version_relation(target_version, current) == "older"

    _clear_update_failed(settings)
    _set_update_lock(settings)
    _write_update_pending(
        settings,
        from_version=current,
        to_version=target_version,
        target_image=target_image,
        is_downgrade=is_downgrade,
    )
    _write_update_progress(
        settings,
        {
            "operation": "update",
            "stage": "starting",
            "message": t("api.update.preparing_update"),
            "from_version": current,
            "to_version": target_version,
        },
    )
    try:
        _spawn_updater(
            settings,
            target_image=target_image,
            from_version=current,
            to_version=target_version,
        )
    except OSError as exc:
        _lock_path(settings).unlink(missing_ok=True)
        (_data_dir(settings) / UPDATE_PENDING_FILE).unlink(missing_ok=True)
        _clear_update_progress(settings)
        log.exception("Failed to spawn updater")
        raise api_error("api.update.start_failed", 500, error=str(exc)) from exc

    payload = localize_payload(
        {
            "status": "accepted",
            "target_version": target_version,
            "is_downgrade": is_downgrade,
            "message": t("api.update.update_started"),
        }
    )
    return Response(status_code=202, content=json.dumps(payload), media_type="application/json")


@router.post("/update/restore", status_code=202)
async def restore_update_backup(
    body: RestoreBackupRequest | None = None,
    _admin: SessionUser = Depends(require_admin),
    settings: Settings = Depends(get_settings),
) -> Response:
    if not _can_apply(settings):
        raise api_error("api.update.restore_disabled", 403)
    if _update_in_progress(settings):
        raise api_error("api.update.already_in_progress", 409)

    backups = _list_backups(settings)
    if not backups:
        raise api_error("api.update.no_backups", 404)

    backup_name = body.backup if body and body.backup else backups[0]["name"]
    if not any(b["name"] == backup_name for b in backups):
        raise api_error("api.update.backup_not_found", 404)

    deploy_state = _load_deploy_state(settings) or {}
    pending = _read_json_file(_data_dir(settings) / UPDATE_PENDING_FILE) or {}
    restore_image = _resolve_restore_image(settings, deploy_state, pending)
    if not restore_image:
        raise api_error("api.update.restore_image_unknown", 400)

    _clear_update_failed(settings)
    _set_update_lock(settings)
    _write_update_progress(
        settings,
        {
            "operation": "restore",
            "stage": "starting",
            "message": t("api.update.preparing_restore"),
            "from_version": _image_version(str(restore_image)),
            "to_version": _image_version(str(restore_image)),
        },
    )
    try:
        _spawn_restore(
            settings,
            backup_name=backup_name,
            restore_image=str(restore_image),
        )
    except OSError as exc:
        _lock_path(settings).unlink(missing_ok=True)
        _clear_update_progress(settings)
        log.exception("Failed to spawn restore")
        raise api_error("api.update.restore_start_failed", 500, error=str(exc)) from exc

    payload = localize_payload(
        {
            "status": "accepted",
            "backup": backup_name,
            "message": t("api.update.restore_started"),
        }
    )
    return Response(status_code=202, content=json.dumps(payload), media_type="application/json")
