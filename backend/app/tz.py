"""Site timezone resolution and helpers."""

from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx

log = logging.getLogger("tz")

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"


def resolve_site_tz(name: str, *, auto_hint: str | None = None) -> ZoneInfo:
    """Return ZoneInfo for an IANA name or auto (using optional hint)."""
    normalized = (name or "").strip()
    if not normalized or normalized.lower() == "auto":
        if auto_hint:
            try:
                return ZoneInfo(auto_hint)
            except (ZoneInfoNotFoundError, ValueError):
                log.debug("Invalid auto_hint timezone %r; falling back to UTC", auto_hint)
        else:
            log.debug("Site timezone is auto with no resolved hint; using UTC")
        return ZoneInfo("UTC")
    try:
        return ZoneInfo(normalized)
    except (ZoneInfoNotFoundError, ValueError):
        log.warning("Invalid site timezone %r; falling back to UTC", normalized)
        return ZoneInfo("UTC")


def to_site_local(dt: datetime, tz: ZoneInfo) -> datetime:
    return dt.astimezone(tz)


async def fetch_auto_timezone(
    lat: float,
    lon: float,
    client: httpx.AsyncClient,
) -> str | None:
    """Resolve IANA timezone from coordinates via Open-Meteo."""
    if lat == 0.0 and lon == 0.0:
        return None
    try:
        resp = await client.get(
            OPEN_METEO_URL,
            params={
                "latitude": lat,
                "longitude": lon,
                "timezone": "auto",
                "forecast_days": 1,
                "hourly": "temperature_2m",
            },
        )
        resp.raise_for_status()
        tz_name = resp.json().get("timezone")
        if isinstance(tz_name, str) and tz_name.strip():
            return tz_name.strip()
    except Exception as e:  # noqa: BLE001
        log.warning("Failed to fetch auto timezone (%s)", e)
    return None
