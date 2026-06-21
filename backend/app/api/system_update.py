"""Software update checks (GitHub releases) and opt-in Docker self-update."""

from __future__ import annotations

import logging
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response

from .. import __version__
from ..config import Settings, get_settings
from .session import SessionUser, require_admin

log = logging.getLogger("api.system_update")

router = APIRouter(prefix="/api/system", tags=["system"])

GITHUB_RELEASES_LATEST = (
    "https://api.github.com/repos/oraad/solar-ai-optimizer/releases/latest"
)
DOCKER_SOCKET = Path("/var/run/docker.sock")
UPDATE_LOCK_FILE = ".update_in_progress"
RELEASE_CACHE_TTL_SECONDS = 15 * 60

_release_cache: dict[str, Any] | None = None
_release_cache_at: float = 0.0

DeploymentKind = Literal["addon", "docker", "compose", "unknown"]


def _parse_version(version: str) -> tuple[int, int, int]:
    cleaned = version.lstrip("vV").strip()
    match = re.match(r"^(\d+)(?:\.(\d+))?(?:\.(\d+))?", cleaned)
    if not match:
        return (0, 0, 0)
    return tuple(int(part or 0) for part in match.groups())


def _is_newer(latest: str, current: str) -> bool:
    return _parse_version(latest) > _parse_version(current)


def _docker_socket_available() -> bool:
    try:
        return DOCKER_SOCKET.is_socket()
    except OSError:
        return False


def _detect_deployment(settings: Settings) -> DeploymentKind:
    if settings.is_addon:
        return "addon"
    if settings.self_update_enabled and _docker_socket_available():
        return "docker"
    if Path("/app/run.sh").is_file() and not settings.self_update_enabled:
        return "compose"
    return "unknown"


def _can_apply(settings: Settings) -> bool:
    return (
        settings.self_update_enabled
        and _docker_socket_available()
        and not settings.is_addon
    )


def _apply_instructions(deployment: DeploymentKind) -> str | None:
    if deployment == "addon":
        return (
            "Update via the Home Assistant Supervisor: Settings → Add-ons → "
            "Solar AI Optimizer → Update."
        )
    if deployment == "docker":
        return None
    if deployment == "compose":
        return (
            "From the project directory:\n"
            "  docker compose pull\n"
            "  docker compose up -d --build\n\n"
            "Or enable self-update with docker-compose.self-update.yml "
            "(see docs/installation.md)."
        )
    return (
        "On Proxmox LXC, run: update\n\n"
        "Or manually:\n"
        "  docker pull ghcr.io/oraad/solar-ai-optimizer:latest\n"
        "  docker stop solar-optimizer && docker rm solar-optimizer\n"
        "  docker run -d --name solar-optimizer --restart unless-stopped \\\n"
        "    --env-file /opt/solar-ai-optimizer/solar.env \\\n"
        "    -v solar-data:/app/data -p 8000:8000 \\\n"
        "    ghcr.io/oraad/solar-ai-optimizer:latest"
    )


async def _fetch_latest_release() -> dict[str, Any] | None:
    global _release_cache, _release_cache_at

    now = time.monotonic()
    if _release_cache is not None and now - _release_cache_at < RELEASE_CACHE_TTL_SECONDS:
        return _release_cache

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
        return _release_cache

    _release_cache = data
    _release_cache_at = now
    return data


def _lock_path(settings: Settings) -> Path:
    return Path(settings.data_dir) / UPDATE_LOCK_FILE


def _update_in_progress(settings: Settings) -> bool:
    return _lock_path(settings).exists()


def _set_update_lock(settings: Settings) -> None:
    Path(settings.data_dir).mkdir(parents=True, exist_ok=True)
    _lock_path(settings).write_text(str(time.time()), encoding="utf-8")


def _build_updater_shell(settings: Settings) -> str:
    """Shell script run inside a transient docker:cli container on the host."""
    env_file = settings.self_update_env_file.strip().replace("'", "'\\''")
    return f"""set -e
IMAGE='{settings.self_update_image}'
CONTAINER='{settings.self_update_container}'
ENV_FILE='{env_file}'
DATA_VOL='{settings.self_update_data_volume}'
DATA_PATH='{settings.self_update_data_path}'
PORT='{settings.self_update_port}'

docker pull "$IMAGE"

ENV_ARGS=""
ENV_TMP=""
if [ -n "$ENV_FILE" ]; then
  ENV_ARGS="--env-file $ENV_FILE"
elif docker inspect "$CONTAINER" >/dev/null 2>&1; then
  ENV_TMP="/tmp/solar-update-env-$$"
  docker inspect -f '{{{{range .Config.Env}}}}{{{{println .}}}}{{{{end}}}}' "$CONTAINER" > "$ENV_TMP"
  ENV_ARGS="--env-file $ENV_TMP"
fi

docker stop "$CONTAINER" 2>/dev/null || true
docker rm "$CONTAINER" 2>/dev/null || true

docker volume inspect "$DATA_VOL" >/dev/null 2>&1 || docker volume create "$DATA_VOL" >/dev/null

docker run -d --name "$CONTAINER" --restart unless-stopped \\
  $ENV_ARGS \\
  -e SELF_UPDATE_ENABLED=true \\
  -e SELF_UPDATE_ENV_FILE="$ENV_FILE" \\
  -v /var/run/docker.sock:/var/run/docker.sock \\
  -v "${{DATA_VOL}}:${{DATA_PATH}}" \\
  -p "${{PORT}}:8000" \\
  "$IMAGE"

rm -f "$ENV_TMP" 2>/dev/null || true
"""


def _spawn_updater(settings: Settings) -> None:
    script = _build_updater_shell(settings)
    cmd = [
        "docker",
        "run",
        "-d",
        "--rm",
        "-v",
        f"{DOCKER_SOCKET}:{DOCKER_SOCKET}",
        "-v",
        "/tmp:/tmp",
        "docker:cli",
        "sh",
        "-c",
        script,
    ]
    log.info("Spawning self-update container for image %s", settings.self_update_image)
    subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


async def build_update_info(settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    current = __version__
    deployment = _detect_deployment(settings)
    can_apply = _can_apply(settings)

    release = await _fetch_latest_release()
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

    return {
        "current_version": current,
        "latest_version": latest_version,
        "update_available": update_available,
        "release_notes": release_notes,
        "release_url": release_url,
        "published_at": published_at,
        "can_apply": can_apply,
        "deployment": deployment,
        "apply_instructions": _apply_instructions(deployment),
        "update_in_progress": _update_in_progress(settings),
    }


@router.get("/update")
async def get_update_info(
    _admin: SessionUser = Depends(require_admin),
) -> dict[str, Any]:
    return await build_update_info()


@router.post("/update", status_code=202)
async def apply_update(
    _admin: SessionUser = Depends(require_admin),
    settings: Settings = Depends(get_settings),
) -> Response:
    if not _can_apply(settings):
        raise HTTPException(
            status_code=403,
            detail="Self-update is not enabled for this deployment.",
        )
    if _update_in_progress(settings):
        raise HTTPException(status_code=409, detail="Update already in progress.")

    info = await build_update_info(settings)
    if not info.get("update_available"):
        raise HTTPException(status_code=400, detail="Already on the latest release.")

    _set_update_lock(settings)
    try:
        _spawn_updater(settings)
    except OSError as exc:
        _lock_path(settings).unlink(missing_ok=True)
        log.exception("Failed to spawn updater")
        raise HTTPException(status_code=500, detail=f"Failed to start update: {exc}") from exc

    return Response(
        status_code=202,
        content='{"status":"accepted","message":"Update started; service will restart."}',
        media_type="application/json",
    )
