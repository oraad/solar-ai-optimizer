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
MIN_SELF_UPDATE_VERSION = "0.5.5"
RELEASES_LIST_LIMIT = 20

DOWNGRADE_WARNING = (
    "Installing an older release will restart the service. A backup of /app/data is "
    "created automatically before every install. Downgrading may be incompatible if "
    "config or database schema changed since that version."
)

MISSING_DOCKER_CLI_DETAIL = (
    "Docker CLI is not available in this container. Pull "
    "ghcr.io/oraad/solar-ai-optimizer:latest (v0.5.5+) and recreate the "
    "container once manually; see docs/installation.md."
)
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
        return (
            "Update via the Home Assistant Supervisor: Settings → Add-ons → "
            "Solar AI Optimizer → Update."
        )
    if deployment in ("docker", "proxmox"):
        if not _docker_cli_available():
            return MISSING_DOCKER_CLI_DETAIL
        return None
    if deployment == "compose":
        if version:
            return (
                f"From the project directory:\n"
                f"  docker pull {image}\n"
                f"  docker compose up -d --build\n\n"
                f"Or set SELF_UPDATE_IMAGE={image} and enable self-update "
                f"(see docs/installation.md)."
            )
        return (
            "From the project directory:\n"
            "  docker compose pull\n"
            "  docker compose up -d --build\n\n"
            "Or enable self-update with docker-compose.self-update.yml "
            "(see docs/installation.md)."
        )
    if version:
        return (
            f"On Proxmox LXC, run: update\n\n"
            f"Or manually:\n"
            f"  docker pull {image}\n"
            f"  docker stop solar-optimizer && docker rm solar-optimizer\n"
            f"  docker run -d --name solar-optimizer --restart unless-stopped \\\n"
            f"    --env-file /opt/solar-ai-optimizer/solar.env \\\n"
            f"    -v solar-data:/app/data -p 8000:8000 \\\n"
            f"    {image}"
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


def _shell_progress_block(operation: str) -> str:
    """Shell helpers to write UPDATE_PROGRESS_FILE on the data volume."""
    return f"""
PROGRESS_FILE='{UPDATE_PROGRESS_FILE}'
OPERATION='{operation}'
STARTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u)"

write_progress() {{
  local stage="$1" msg="$2" detail="${{3:-}}"
  local updated detail_json
  updated="$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u)"
  detail_json=""
  if [ -n "$detail" ]; then
    detail_json=$(printf ', "pull_detail": "%s"' "$(printf '%s' "$detail" | tr '\\n' ' ' | sed 's/\\\\/\\\\\\\\/g; s/"/\\\\"/g')")
  fi
  docker run --rm -i -v "${{DATA_VOL}}:/data" alpine sh -c "cat > /data/$PROGRESS_FILE" <<WPEOF
{{"operation":"$OPERATION","stage":"$stage","message":"$msg"$detail_json,"from_version":"$FROM_VERSION","to_version":"$TO_VERSION","started_at":"$STARTED_AT","updated_at":"$updated"}}
WPEOF
}}

mark_progress_failed() {{
  write_progress "failed" "$1" || true
}}
"""


def _shell_run_container_block() -> str:
    """Start solar-optimizer with a given image tag (rollback uses PREVIOUS_IMAGE)."""
    return """
run_container() {
  local image="$1"
  docker run -d --name "$CONTAINER" --restart unless-stopped \\
    $ENV_ARGS \\
    -e SELF_UPDATE_ENABLED=true \\
    -e SELF_UPDATE_ENV_FILE="$ENV_FILE" \\
    -e SELF_UPDATE_IMAGE="$image" \\
    -v /var/run/docker.sock:/var/run/docker.sock \\
    -v "${DATA_VOL}:${DATA_PATH}" \\
    -p "${PORT}:8000" \\
    "$image"
}

try_recreate_container() {
  local target_image="$1"
  write_progress "recreating" "Starting updated container"
  if run_container "$target_image"; then
    return 0
  fi
  if [ -n "$PREVIOUS_IMAGE" ]; then
    write_progress "recreating" "Rolling back to previous container image"
    docker rm -f "$CONTAINER" 2>/dev/null || true
    if run_container "$PREVIOUS_IMAGE"; then
      fail "new image failed to start; rolled back to previous image"
    fi
  fi
  fail "container recreate failed"
}
"""


def _build_updater_shell(
    settings: Settings,
    *,
    target_image: str,
    from_version: str,
    to_version: str,
) -> str:
    """Shell script run inside a transient docker:cli container on the host."""
    env_file = settings.self_update_env_file.strip().replace("'", "'\\''")
    target_image_esc = target_image.replace("'", "'\\''")
    from_version_esc = from_version.replace("'", "'\\''")
    to_version_esc = to_version.replace("'", "'\\''")
    deploy_state_esc = DEPLOY_STATE_FILE.replace("'", "'\\''")
    return f"""set -e
TARGET_IMAGE='{target_image_esc}'
FROM_VERSION='{from_version_esc}'
TO_VERSION='{to_version_esc}'
CONTAINER='{settings.self_update_container}'
ENV_FILE='{env_file}'
DATA_VOL='{settings.self_update_data_volume}'
DATA_PATH='{settings.self_update_data_path}'
PORT='{settings.self_update_port}'
BACKUP_DIR='{BACKUP_DIR}'
DEPLOY_STATE='{deploy_state_esc}'
LOCK_FILE='{UPDATE_LOCK_FILE}'
PENDING_FILE='{UPDATE_PENDING_FILE}'
FAILED_FILE='{UPDATE_FAILED_FILE}'
{_shell_progress_block("update")}
{_shell_run_container_block()}

fail() {{
  MSG="$1"
  mark_progress_failed "$MSG"
  docker run --rm -i -v "${{DATA_VOL}}:/data" alpine sh -c "cat > /data/$FAILED_FILE" <<FAILJSON
{{"message":"$MSG","backup":"$BACKUP"}}
FAILJSON
  docker run --rm -v "${{DATA_VOL}}:/data" alpine rm -f "/data/$LOCK_FILE" "/data/$PENDING_FILE" "/data/$PROGRESS_FILE" 2>/dev/null || true
  exit 1
}}

write_progress "starting" "Preparing update"

BACKUP="${{BACKUP_DIR}}/pre-from-${{FROM_VERSION}}-to-${{TO_VERSION}}-$(date +%s).tar.gz"
write_progress "backing_up" "Backing up data"
docker run --rm -v "${{DATA_VOL}}:/data" alpine sh -c \\
  "mkdir -p /data/${{BACKUP_DIR}} && tar czf /data/${{BACKUP}} -C /data --exclude=${{BACKUP_DIR}} ." \\
  || fail "backup failed"

docker run --rm -v "${{DATA_VOL}}:/data" alpine sh -c \\
  'cd /data/'"${{BACKUP_DIR}}"' && ls -1t pre-*.tar.gz 2>/dev/null | tail -n +{BACKUP_RETENTION + 1} | while read f; do rm -f "$f"; done' \\
  || true

write_progress "pulling" "Pulling $TARGET_IMAGE"
docker pull --progress=plain "$TARGET_IMAGE" 2>&1 | tee /tmp/solar-pull.log || fail "docker pull failed"
PULL_LAST="$(grep -v '^$' /tmp/solar-pull.log 2>/dev/null | tail -1 || true)"
write_progress "pulling" "Pulling $TARGET_IMAGE" "$PULL_LAST"

PREVIOUS_IMAGE=""
if docker inspect "$CONTAINER" >/dev/null 2>&1; then
  PREVIOUS_IMAGE=$(docker inspect -f '{{{{.Config.Image}}}}' "$CONTAINER" 2>/dev/null || echo "")
fi

ENV_ARGS=""
ENV_TMP=""
if [ -n "$ENV_FILE" ]; then
  ENV_ARGS="--env-file $ENV_FILE"
elif docker inspect "$CONTAINER" >/dev/null 2>&1; then
  ENV_TMP="/tmp/solar-update-env-$$"
  docker inspect -f '{{{{range .Config.Env}}}}{{{{println .}}}}{{{{end}}}}' "$CONTAINER" > "$ENV_TMP"
  ENV_ARGS="--env-file $ENV_TMP"
fi

write_progress "stopping" "Stopping current container"
docker stop "$CONTAINER" 2>/dev/null || true
docker rm "$CONTAINER" 2>/dev/null || true

docker volume inspect "$DATA_VOL" >/dev/null 2>&1 || docker volume create "$DATA_VOL" >/dev/null

try_recreate_container "$TARGET_IMAGE"

rm -f "$ENV_TMP" 2>/dev/null || true

write_progress "finishing" "Finalizing"

DEPLOY_JSON=$(cat <<EOF
{{
  "version": "$TO_VERSION",
  "image": "$TARGET_IMAGE",
  "previous_version": "$FROM_VERSION",
  "previous_image": "$PREVIOUS_IMAGE",
  "deployed_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "last_backup": "$BACKUP",
  "restored_from_backup": false
}}
EOF
)
docker run --rm -i -v "${{DATA_VOL}}:/data" alpine sh -c "cat > /data/$DEPLOY_STATE" <<< "$DEPLOY_JSON" || true

docker run --rm -v "${{DATA_VOL}}:/data" alpine rm -f "/data/$LOCK_FILE" "/data/$PENDING_FILE" "/data/$FAILED_FILE" "/data/$PROGRESS_FILE" 2>/dev/null || true
"""


def _build_restore_shell(
    settings: Settings,
    *,
    backup_name: str,
    restore_image: str,
    restore_version: str,
) -> str:
    env_file = settings.self_update_env_file.strip().replace("'", "'\\''")
    backup_esc = backup_name.replace("'", "'\\''")
    restore_image_esc = restore_image.replace("'", "'\\''")
    restore_version_esc = restore_version.replace("'", "'\\''")
    deploy_state_esc = DEPLOY_STATE_FILE.replace("'", "'\\''")
    pending_file_esc = UPDATE_PENDING_FILE.replace("'", "'\\''")
    return f"""set -e
BACKUP_NAME='{backup_esc}'
TARGET_IMAGE='{restore_image_esc}'
RESTORE_VERSION='{restore_version_esc}'
FROM_VERSION='{restore_version_esc}'
TO_VERSION='{restore_version_esc}'
CONTAINER='{settings.self_update_container}'
ENV_FILE='{env_file}'
DATA_VOL='{settings.self_update_data_volume}'
DATA_PATH='{settings.self_update_data_path}'
PORT='{settings.self_update_port}'
BACKUP_DIR='{BACKUP_DIR}'
DEPLOY_STATE='{deploy_state_esc}'
LOCK_FILE='{UPDATE_LOCK_FILE}'
PENDING_FILE='{pending_file_esc}'
FAILED_FILE='{UPDATE_FAILED_FILE}'
{_shell_progress_block("restore")}
{_shell_run_container_block()}

fail() {{
  MSG="$1"
  mark_progress_failed "$MSG"
  docker run --rm -i -v "${{DATA_VOL}}:/data" alpine sh -c "cat > /data/$FAILED_FILE" <<FAILJSON
{{"message":"$MSG","backup":"$BACKUP_NAME"}}
FAILJSON
  docker run --rm -v "${{DATA_VOL}}:/data" alpine rm -f "/data/$LOCK_FILE" "/data/$PROGRESS_FILE" 2>/dev/null || true
  exit 1
}}

write_progress "starting" "Preparing restore"

docker run --rm -v "${{DATA_VOL}}:/data" alpine sh -c \\
  "test -f /data/${{BACKUP_DIR}}/$BACKUP_NAME" || fail "backup not found"

PREVIOUS_IMAGE=""
if docker inspect "$CONTAINER" >/dev/null 2>&1; then
  PREVIOUS_IMAGE=$(docker inspect -f '{{{{.Config.Image}}}}' "$CONTAINER" 2>/dev/null || echo "")
fi

ENV_ARGS=""
ENV_TMP=""
if [ -n "$ENV_FILE" ]; then
  ENV_ARGS="--env-file $ENV_FILE"
elif docker inspect "$CONTAINER" >/dev/null 2>&1; then
  ENV_TMP="/tmp/solar-restore-env-$$"
  docker inspect -f '{{{{range .Config.Env}}}}{{{{println .}}}}{{{{end}}}}' "$CONTAINER" > "$ENV_TMP"
  ENV_ARGS="--env-file $ENV_TMP"
fi

write_progress "stopping" "Stopping current container"
docker stop "$CONTAINER" 2>/dev/null || true
docker rm "$CONTAINER" 2>/dev/null || true

write_progress "restoring_data" "Restoring backup data"
docker run --rm -v "${{DATA_VOL}}:/data" alpine sh -c \\
  "cd /data && find . -mindepth 1 -maxdepth 1 ! -name ${{BACKUP_DIR}} -exec rm -rf {{}} +" \\
  || fail "clear data failed"

docker run --rm -v "${{DATA_VOL}}:/data" alpine sh -c \\
  "tar xzf /data/${{BACKUP_DIR}}/$BACKUP_NAME -C /data" \\
  || fail "extract backup failed"

try_recreate_container "$TARGET_IMAGE"

rm -f "$ENV_TMP" 2>/dev/null || true

write_progress "finishing" "Finalizing"

DEPLOY_JSON=$(cat <<EOF
{{
  "version": "$RESTORE_VERSION",
  "image": "$TARGET_IMAGE",
  "previous_version": null,
  "previous_image": null,
  "deployed_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "last_backup": "${{BACKUP_DIR}}/$BACKUP_NAME",
  "restored_from_backup": true
}}
EOF
)
docker run --rm -i -v "${{DATA_VOL}}:/data" alpine sh -c "cat > /data/$DEPLOY_STATE" <<< "$DEPLOY_JSON" || true

docker run --rm -v "${{DATA_VOL}}:/data" alpine rm -f "/data/$LOCK_FILE" "/data/$PENDING_FILE" "/data/$FAILED_FILE" "/data/$PROGRESS_FILE" 2>/dev/null || true
"""


def _spawn_shell(script: str, *, log_label: str) -> None:
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
    log.info("Spawning %s", log_label)
    subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def _spawn_updater(
    settings: Settings,
    *,
    target_image: str,
    from_version: str,
    to_version: str,
) -> None:
    script = _build_updater_shell(
        settings,
        target_image=target_image,
        from_version=from_version,
        to_version=to_version,
    )
    _spawn_shell(script, log_label=f"self-update container for {target_image}")


def _spawn_restore(
    settings: Settings,
    *,
    backup_name: str,
    restore_image: str,
) -> None:
    restore_version = _image_version(restore_image) or __version__
    script = _build_restore_shell(
        settings,
        backup_name=backup_name,
        restore_image=restore_image,
        restore_version=restore_version,
    )
    _spawn_shell(script, log_label=f"restore from backup {backup_name}")


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
            raise HTTPException(status_code=400, detail="Invalid version format.")
        known = {_normalize_version(str(r.get("tag_name", ""))) for r in releases}
        if normalized not in known:
            raise HTTPException(status_code=400, detail="Unknown or unavailable release.")
        return normalized
    if not summaries:
        raise HTTPException(status_code=503, detail="Could not resolve latest release.")
    latest = _normalize_version(str(releases[0].get("tag_name", "")))
    if not latest:
        raise HTTPException(status_code=503, detail="Could not resolve latest release.")
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

    return {
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
        "update_progress": _load_update_progress(settings),
        "release_checked_at": release_checked_at,
        "release_from_cache": release_from_cache,
        "releases": release_summaries,
        "previous_version": previous_version,
        "min_self_update_version": MIN_SELF_UPDATE_VERSION,
        "backups": _list_backups(settings),
        "downgrade_warning": DOWNGRADE_WARNING,
        "update_failed": update_failed,
    }


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
            raise HTTPException(status_code=503, detail=MISSING_DOCKER_CLI_DETAIL)
        raise HTTPException(
            status_code=403,
            detail="Self-update is not enabled for this deployment.",
        )
    if _update_in_progress(settings):
        raise HTTPException(status_code=409, detail="Update already in progress.")

    current = __version__
    releases_raw, _ = await _fetch_releases(force=True)
    target_version = _resolve_target_version(
        releases_raw, body.version if body else None, current
    )

    if _parse_version(target_version) == _parse_version(current):
        raise HTTPException(status_code=400, detail="Already running this version.")
    if _version_below_min(target_version):
        raise HTTPException(
            status_code=400,
            detail=f"Version {target_version} is below minimum {MIN_SELF_UPDATE_VERSION} "
            "for one-click self-update.",
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
            "message": "Preparing update",
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
        raise HTTPException(status_code=500, detail=f"Failed to start update: {exc}") from exc

    payload = {
        "status": "accepted",
        "target_version": target_version,
        "is_downgrade": is_downgrade,
        "message": "Update started; service will restart.",
    }
    return Response(status_code=202, content=json.dumps(payload), media_type="application/json")


@router.post("/update/restore", status_code=202)
async def restore_update_backup(
    body: RestoreBackupRequest | None = None,
    _admin: SessionUser = Depends(require_admin),
    settings: Settings = Depends(get_settings),
) -> Response:
    if not _can_apply(settings):
        raise HTTPException(
            status_code=403,
            detail="Backup restore is not enabled for this deployment.",
        )
    if _update_in_progress(settings):
        raise HTTPException(status_code=409, detail="Update already in progress.")

    backups = _list_backups(settings)
    if not backups:
        raise HTTPException(status_code=404, detail="No backups available.")

    backup_name = body.backup if body and body.backup else backups[0]["name"]
    if not any(b["name"] == backup_name for b in backups):
        raise HTTPException(status_code=404, detail="Backup not found.")

    deploy_state = _load_deploy_state(settings) or {}
    pending = _read_json_file(_data_dir(settings) / UPDATE_PENDING_FILE) or {}
    restore_image = _resolve_restore_image(settings, deploy_state, pending)
    if not restore_image:
        raise HTTPException(status_code=400, detail="Could not determine image for restore.")

    _clear_update_failed(settings)
    _set_update_lock(settings)
    _write_update_progress(
        settings,
        {
            "operation": "restore",
            "stage": "starting",
            "message": "Preparing restore",
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
        raise HTTPException(status_code=500, detail=f"Failed to start restore: {exc}") from exc

    payload = {
        "status": "accepted",
        "backup": backup_name,
        "message": "Restore started; service will restart.",
    }
    return Response(status_code=202, content=json.dumps(payload), media_type="application/json")
