"""HA add-on pre-release update polling when ADDON_PRERELEASE_UPDATES is enabled."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from .. import __version__
from ..api.system_update import (
    _fetch_releases,
    _is_newer,
    _normalize_version,
)
from ..config import Settings

log = logging.getLogger(__name__)

STATE_FILE = ".ha_prerelease_update.json"
POLL_INTERVAL_HOURS = 6
SUPERVISOR_BASE = "http://supervisor"


def _state_path(settings: Settings) -> Path:
    return Path(settings.data_dir) / STATE_FILE


def _read_state(settings: Settings) -> dict[str, Any]:
    path = _state_path(settings)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _write_state(settings: Settings, data: dict[str, Any]) -> None:
    path = _state_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _pick_newest_release(releases: list[dict[str, Any]], current: str) -> str | None:
    best: str | None = None
    for release in releases:
        version = _normalize_version(str(release.get("tag_name", "")))
        if not version or not _is_newer(version, current):
            continue
        if best is None or _is_newer(version, best):
            best = version
    return best


async def _supervisor_headers(settings: Settings) -> dict[str, str]:
    return {"Authorization": f"Bearer {settings.supervisor_token}"}


async def _resolve_addon_slug(client: httpx.AsyncClient, settings: Settings) -> str | None:
    headers = await _supervisor_headers(settings)
    response = await client.get(f"{SUPERVISOR_BASE}/addons/self/info", headers=headers)
    response.raise_for_status()
    payload = response.json()
    data = payload.get("data") if isinstance(payload, dict) else None
    if isinstance(data, dict):
        slug = data.get("slug")
        if isinstance(slug, str) and slug:
            return slug
    return None


async def _request_supervisor_update(
    client: httpx.AsyncClient,
    settings: Settings,
    slug: str,
    target_version: str,
) -> tuple[bool, str]:
    headers = await _supervisor_headers(settings)
    body = {"version": target_version, "background": True}
    for path in (
        f"{SUPERVISOR_BASE}/addons/{slug}/update",
        f"{SUPERVISOR_BASE}/store/addons/{slug}/update",
    ):
        response = await client.post(path, headers=headers, json=body)
        if response.status_code == 403:
            return False, "supervisor_forbidden_self_update"
        if response.is_success:
            return True, path
        if response.status_code not in (404, 405):
            return False, f"http_{response.status_code}"
    return False, "no_supported_endpoint"


def _is_prerelease_version(version: str) -> bool:
    return "-" in version.lstrip("vV").strip().split("+", 1)[0]


async def ha_addon_update_cycle(settings: Settings) -> None:
    if not settings.is_addon:
        return
    if not settings.addon_prerelease_updates:
        if _is_prerelease_version(__version__):
            log.info(
                "Running pre-release %s; enable pre-release updates in app "
                "configuration to check for newer builds, or wait for stable GA.",
                __version__,
            )
        return

    state = _read_state(settings)
    releases, _ = await _fetch_releases(include_prereleases=True, force=True)
    target = _pick_newest_release(releases, __version__)
    if not target:
        return
    if state.get("last_attempted_version") == target and state.get("outcome") == "forbidden":
        return

    log.info("Pre-release update available: %s (current %s)", target, __version__)
    outcome = "notified"
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            slug = await _resolve_addon_slug(client, settings)
            if not slug:
                outcome = "slug_unresolved"
            else:
                ok, detail = await _request_supervisor_update(
                    client, settings, slug, target
                )
                if ok:
                    outcome = "update_requested"
                    log.info("Requested Supervisor update to %s via %s", target, detail)
                elif detail == "supervisor_forbidden_self_update":
                    outcome = "forbidden"
                    log.warning(
                        "Supervisor does not allow in-app self-update to %s. "
                        "Update manually via Settings → Apps → Solar AI Optimizer.",
                        target,
                    )
                else:
                    outcome = detail
                    log.warning(
                        "Could not trigger Supervisor update to %s (%s). "
                        "Update manually via Settings → Apps when available.",
                        target,
                        detail,
                    )
    except httpx.HTTPError as exc:
        outcome = "http_error"
        log.warning("Supervisor pre-release update check failed: %s", exc)

    _write_state(
        settings,
        {
            "last_attempted_version": target,
            "outcome": outcome,
            "current_version": __version__,
        },
    )


def register_ha_addon_update_job(
    scheduler: AsyncIOScheduler,
    settings: Settings,
) -> None:
    if not settings.is_addon:
        return

    async def _job() -> None:
        await ha_addon_update_cycle(settings)

    scheduler.add_job(
        _job,
        IntervalTrigger(hours=POLL_INTERVAL_HOURS),
        id="ha_addon_prerelease_update",
        max_instances=1,
        coalesce=True,
        next_run_time=datetime.now(UTC) + timedelta(minutes=2),
    )
