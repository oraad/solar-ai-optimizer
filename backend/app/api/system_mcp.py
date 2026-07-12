"""Admin MCP settings (mcp.env) and container restart/recreate."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from ..config import Settings, get_settings
from ..i18n import api_error, t
from ..mcp.credentials import (
    generate_mcp_token,
    mcp_env_path,
    read_mcp_env,
    write_mcp_env,
)
from ..observability.metrics import metrics
from .session import SessionUser, require_admin
from .system_update import (
    _can_apply,
    _current_container_image,
    _docker_cli_available,
    _update_in_progress,
)

log = logging.getLogger("api.system_mcp")

router = APIRouter(prefix="/api/system", tags=["system"])

MCP_PENDING_FILE = ".mcp_restart_pending"

RecommendedAction = Literal["restart", "recreate", "manual", "none"]


class McpSettingsUpdate(BaseModel):
    enabled: bool
    token: str | None = None
    clear_token: bool = False
    generate_token: bool = False


def _data_dir(settings: Settings) -> Path:
    return Path(settings.data_dir)


def _pending_path(settings: Settings) -> Path:
    return _data_dir(settings) / MCP_PENDING_FILE


def _set_pending(settings: Settings) -> None:
    _data_dir(settings).mkdir(parents=True, exist_ok=True)
    _pending_path(settings).write_text("1\n", encoding="utf-8")


def _clear_pending(settings: Settings) -> None:
    path = _pending_path(settings)
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def _pending_mcp_env(settings: Settings) -> bool:
    if not _pending_path(settings).is_file():
        return False
    stored = read_mcp_env(settings.data_dir)
    if not stored:
        return True
    want_enabled = stored.get("MCP_ENABLED", "false").lower() in ("1", "true", "yes")
    want_token = (stored.get("MCP_TOKEN") or "").strip()
    if settings.mcp_enabled != want_enabled:
        return True
    if want_token and want_token != settings.mcp_token:
        return True
    if not want_token and settings.mcp_token and "MCP_TOKEN" in stored:
        # Explicit empty token in file vs live token
        return bool(settings.mcp_token)
    _clear_pending(settings)
    return False


def _can_restart(settings: Settings) -> bool:
    return _can_apply(settings)


def _can_recreate(settings: Settings) -> bool:
    return _can_apply(settings)


def _recommended_action(
    settings: Settings, *, pending: bool
) -> RecommendedAction:
    if settings.is_addon:
        return "manual"
    if pending and _can_restart(settings):
        return "restart"
    if _can_restart(settings):
        return "none"
    return "manual"


def _mcp_status_payload(request: Request, settings: Settings) -> dict[str, Any]:
    pending = _pending_mcp_env(settings)
    mounted = getattr(request.app.state, "mcp_server", None) is not None
    path = settings.mcp_http_path.rstrip("/") or "/mcp"
    http_url = None
    if mounted:
        http_url = f"{str(request.base_url).rstrip('/')}{path}"
    stored = read_mcp_env(settings.data_dir)
    has_token = bool(settings.effective_mcp_token) or bool(
        (stored.get("MCP_TOKEN") or "").strip()
    )
    can_restart = _can_restart(settings)
    can_recreate = _can_recreate(settings)
    return {
        "enabled": settings.mcp_enabled,
        "has_token": has_token,
        "http_path": path,
        "http_mounted": mounted,
        "http_url": http_url,
        "tool_calls": metrics.mcp_tool_calls_total,
        "auth_failures": metrics.mcp_auth_failures_total,
        "is_addon": settings.is_addon,
        "editable": not settings.is_addon,
        "can_restart": can_restart,
        "can_recreate": can_recreate,
        "recommended_action": _recommended_action(settings, pending=pending),
        "pending": {"mcp_env": pending},
        "restart_required": pending,
    }


@router.get("/mcp")
async def get_mcp_settings(
    request: Request,
    _admin: SessionUser = Depends(require_admin),
) -> dict[str, Any]:
    return _mcp_status_payload(request, get_settings())


@router.put("/mcp")
async def put_mcp_settings(
    request: Request,
    body: McpSettingsUpdate,
    _admin: SessionUser = Depends(require_admin),
) -> dict[str, Any]:
    settings = get_settings()
    if settings.is_addon:
        raise api_error("api.mcp.addon_readonly", 403)

    if _update_in_progress(settings):
        raise api_error("api.update.already_in_progress", 409)

    generated: str | None = None
    clear = body.clear_token
    token: str | None = body.token
    if body.generate_token:
        generated = generate_mcp_token()
        token = generated
        clear = False
    elif token is not None and not token.strip():
        token = None  # blank = keep existing

    if body.enabled and not clear:
        effective = token
        if effective is None:
            existing = read_mcp_env(settings.data_dir).get("MCP_TOKEN", "")
            effective = existing or settings.effective_mcp_token
        if not effective:
            raise api_error("api.mcp.token_required", 400)

    path = mcp_env_path(settings.data_dir)
    write_mcp_env(
        path,
        enabled=body.enabled,
        token=token,
        clear_token=clear,
    )
    _set_pending(settings)
    log.info("MCP settings written to %s (enabled=%s)", path, body.enabled)

    out: dict[str, Any] = {
        "ok": True,
        "restart_required": True,
        **_mcp_status_payload(request, settings),
    }
    # Pending reflects disk; live settings still old until restart.
    out["pending"] = {"mcp_env": True}
    out["restart_required"] = True
    out["recommended_action"] = (
        "restart" if _can_restart(settings) else "manual"
    )
    if generated is not None:
        out["token"] = generated
    return out


def _require_lifecycle(settings: Settings) -> None:
    if settings.is_addon:
        raise api_error("api.mcp.addon_lifecycle", 403)
    if not _can_apply(settings):
        raise api_error("api.mcp.lifecycle_unavailable", 503)
    if not _docker_cli_available():
        raise api_error(
            "api.update.docker_cli_missing",
            503,
            min_version="0.5.10",
        )
    if _update_in_progress(settings):
        raise api_error("api.update.already_in_progress", 409)


@router.post("/restart")
async def restart_service(
    _admin: SessionUser = Depends(require_admin),
) -> dict[str, Any]:
    settings = get_settings()
    _require_lifecycle(settings)
    container = settings.self_update_container
    log.info("Admin requested docker restart of %s", container)
    try:
        result = subprocess.run(
            ["docker", "restart", container],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        log.exception("docker restart failed")
        raise api_error("api.mcp.restart_failed", 500, detail=str(exc)) from exc
    if result.returncode != 0:
        log.error("docker restart failed: %s", result.stderr)
        detail = (result.stderr or result.stdout or "").strip()[:500]
        raise api_error("api.mcp.restart_failed", 500, detail=detail)
    return {
        "ok": True,
        "action": "restart",
        "message": t("api.mcp.restart_started"),
    }


@router.post("/recreate")
async def recreate_service(
    _admin: SessionUser = Depends(require_admin),
) -> dict[str, Any]:
    """Same-image recreate preferring host --env-file (re-reads solar.env)."""
    settings = get_settings()
    _require_lifecycle(settings)
    container = settings.self_update_container
    env_file = settings.self_update_env_file.strip()
    image = _current_container_image(settings) or settings.self_update_image
    data_vol = settings.self_update_data_volume
    data_path = settings.self_update_data_path
    port = settings.self_update_port

    log.info("Admin requested recreate of %s from %s", container, image)
    stop = subprocess.run(
        ["docker", "stop", container],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if stop.returncode != 0:
        log.warning("docker stop: %s", stop.stderr)
    subprocess.run(
        ["docker", "rm", container],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    cmd: list[str] = [
        "docker",
        "run",
        "-d",
        "--name",
        container,
        "--restart",
        "unless-stopped",
        "-v",
        f"{data_vol}:{data_path}",
        "-p",
        f"{port}:8000",
        "-v",
        "/var/run/docker.sock:/var/run/docker.sock",
        "-e",
        "SELF_UPDATE_ENABLED=true",
        "-e",
        f"SELF_UPDATE_ENV_FILE={env_file}",
        "-e",
        f"SELF_UPDATE_IMAGE={image}",
    ]
    if env_file:
        cmd.extend(["--env-file", env_file])
    cmd.append(image)

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=180, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        log.exception("docker recreate failed")
        raise api_error("api.mcp.recreate_failed", 500, detail=str(exc)) from exc
    if result.returncode != 0:
        log.error("docker run failed: %s", result.stderr)
        detail = (result.stderr or result.stdout or "").strip()[:500]
        raise api_error("api.mcp.recreate_failed", 500, detail=detail)
    return {
        "ok": True,
        "action": "recreate",
        "message": t("api.mcp.recreate_started"),
    }
