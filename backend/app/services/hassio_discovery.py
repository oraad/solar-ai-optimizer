"""Publish Home Assistant Supervisor discovery for the Solar add-on."""

from __future__ import annotations

import logging

import httpx

from ..auth.install_id import get_or_create_install_id
from ..config import Settings

log = logging.getLogger("services.hassio_discovery")

ADDON_SLUG = "solar_ai_optimizer"
SUPERVISOR_DISCOVERY_URL = "http://supervisor/discovery"
SUPERVISOR_SELF_INFO_URL = "http://supervisor/addons/self/info"
DEFAULT_PORT = 8000


def addon_hostname_from_slug(slug: str = ADDON_SLUG) -> str:
    """HA DNS hostname uses dashes where the slug uses underscores."""
    return slug.replace("_", "-")


async def publish_hassio_discovery(settings: Settings) -> None:
    """POST discovery so the HA integration can auto-setup. Soft-fail on errors."""
    if not settings.is_addon or not settings.supervisor_token:
        return

    headers = {"Authorization": f"Bearer {settings.supervisor_token}"}
    install_id = get_or_create_install_id(settings.data_dir)
    hostname = addon_hostname_from_slug()

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                info = await client.get(SUPERVISOR_SELF_INFO_URL, headers=headers)
                if info.is_success:
                    payload = info.json()
                    data = payload.get("data") if isinstance(payload, dict) else None
                    if isinstance(data, dict):
                        host = data.get("hostname")
                        if isinstance(host, str) and host.strip():
                            hostname = host.strip()
            except Exception:  # noqa: BLE001
                log.debug("Could not resolve add-on hostname from supervisor", exc_info=True)

            uri = f"http://{hostname}:{DEFAULT_PORT}"
            body = {
                "service": ADDON_SLUG,
                "config": {"uri": uri, "install_id": install_id},
            }
            resp = await client.post(
                SUPERVISOR_DISCOVERY_URL,
                headers=headers,
                json=body,
            )
            if resp.is_success:
                log.info(
                    "Published hassio discovery service=%s uri=%s install_id=%s",
                    ADDON_SLUG,
                    uri,
                    install_id,
                )
            else:
                log.warning(
                    "Hassio discovery publish failed: HTTP %s %s",
                    resp.status_code,
                    resp.text[:200],
                )
    except Exception as exc:  # noqa: BLE001
        log.warning("Hassio discovery publish failed: %s", exc)
