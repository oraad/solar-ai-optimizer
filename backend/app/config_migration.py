"""Runtime config override schema versioning and migration."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable

import yaml

log = logging.getLogger("config_migration")

CURRENT_SCHEMA_VERSION = 5
SCHEMA_VERSION_KEY = "schema_version"
OVERRIDES_KEY = "overrides"


def _detect_version(raw: dict[str, Any]) -> int:
    if not raw:
        return CURRENT_SCHEMA_VERSION
    if SCHEMA_VERSION_KEY in raw:
        return int(raw.get(SCHEMA_VERSION_KEY, 0))
    return 0


def migrate_v0_to_v1(overrides: dict[str, Any]) -> dict[str, Any]:
    """Legacy flat overrides — wrap into v1 shape."""
    return dict(overrides)


def migrate_v1_to_v2(overrides: dict[str, Any]) -> dict[str, Any]:
    """Drop removed keys; migrate max_charge_a -> max_grid_charge_a."""
    out = dict(overrides)

    battery = out.get("battery")
    if isinstance(battery, dict):
        battery = dict(battery)
        legacy_max = battery.pop("max_charge_a", None)
        if legacy_max is not None:
            current = battery.get("max_grid_charge_a")
            if current is None:
                battery["max_grid_charge_a"] = legacy_max
            else:
                battery["max_grid_charge_a"] = max(float(current), float(legacy_max))
            log.info(
                "Migrated battery.max_charge_a -> max_grid_charge_a (%s A)",
                battery["max_grid_charge_a"],
            )
        out["battery"] = battery

    inverter = out.get("inverter")
    if isinstance(inverter, dict):
        inverter = dict(inverter)
        write = inverter.get("write")
        if isinstance(write, dict) and "work_mode" in write:
            write = dict(write)
            del write["work_mode"]
            inverter["write"] = write
            log.info("Removed deprecated inverter.write.work_mode from overrides")
        if "work_modes" in inverter:
            del inverter["work_modes"]
            log.info("Removed deprecated inverter.work_modes from overrides")
        out["inverter"] = inverter

    return out


def migrate_v2_to_v3(overrides: dict[str, Any]) -> dict[str, Any]:
    """Move max_grid_charge_a from battery to grid_charge."""
    out = dict(overrides)

    battery = out.get("battery")
    if not isinstance(battery, dict):
        return out

    battery = dict(battery)
    legacy_max = battery.pop("max_grid_charge_a", None)
    if legacy_max is None:
        return out

    grid_charge = out.get("grid_charge")
    if not isinstance(grid_charge, dict):
        grid_charge = {}
    else:
        grid_charge = dict(grid_charge)

    if grid_charge.get("max_grid_charge_a") is None:
        grid_charge["max_grid_charge_a"] = legacy_max
        log.info(
            "Migrated battery.max_grid_charge_a -> grid_charge.max_grid_charge_a (%s A)",
            legacy_max,
        )
    out["grid_charge"] = grid_charge
    out["battery"] = battery
    return out


def migrate_v3_to_v4(overrides: dict[str, Any]) -> dict[str, Any]:
    """Move forecast.timezone to site.timezone."""
    out = dict(overrides)
    forecast = out.get("forecast")
    if not isinstance(forecast, dict):
        return out

    forecast = dict(forecast)
    legacy_tz = forecast.pop("timezone", None)
    if legacy_tz is None:
        return out

    site = out.get("site")
    if not isinstance(site, dict):
        site = {}
    else:
        site = dict(site)

    if site.get("timezone") is None:
        site["timezone"] = legacy_tz
        log.info("Migrated forecast.timezone -> site.timezone (%s)", legacy_tz)

    out["site"] = site
    out["forecast"] = forecast
    return out


def migrate_v4_to_v5(overrides: dict[str, Any]) -> dict[str, Any]:
    """Move forecast.latitude/longitude to site."""
    out = dict(overrides)
    forecast = out.get("forecast")
    if not isinstance(forecast, dict):
        return out

    forecast = dict(forecast)
    legacy_lat = forecast.pop("latitude", None)
    legacy_lon = forecast.pop("longitude", None)
    if legacy_lat is None and legacy_lon is None:
        return out

    site = out.get("site")
    if not isinstance(site, dict):
        site = {}
    else:
        site = dict(site)

    if legacy_lat is not None and site.get("latitude") is None:
        site["latitude"] = legacy_lat
        log.info("Migrated forecast.latitude -> site.latitude (%s)", legacy_lat)
    if legacy_lon is not None and site.get("longitude") is None:
        site["longitude"] = legacy_lon
        log.info("Migrated forecast.longitude -> site.longitude (%s)", legacy_lon)

    out["site"] = site
    out["forecast"] = forecast
    return out


def migrate_config_data(data: dict[str, Any]) -> dict[str, Any]:
    """Apply structural migrations to base YAML / merged config dicts."""
    if not data:
        return {}
    data = migrate_v3_to_v4(dict(data))
    return migrate_v4_to_v5(data)


MIGRATIONS: list[tuple[int, int, Callable[[dict[str, Any]], dict[str, Any]]]] = [
    (0, 1, migrate_v0_to_v1),
    (1, 2, migrate_v1_to_v2),
    (2, 3, migrate_v2_to_v3),
    (3, 4, migrate_v3_to_v4),
    (4, 5, migrate_v4_to_v5),
]


def migrate_overrides(raw: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """Return (overrides_dict, final_schema_version)."""
    version = _detect_version(raw)
    if version == 0:
        overrides = dict(raw)
    else:
        overrides = dict(raw.get(OVERRIDES_KEY) or {})

    for from_v, to_v, fn in MIGRATIONS:
        if version == from_v:
            overrides = fn(overrides)
            version = to_v

    if version != CURRENT_SCHEMA_VERSION:
        log.warning(
            "Runtime overrides schema v%s is newer than supported v%s; "
            "using overrides as-is.",
            version,
            CURRENT_SCHEMA_VERSION,
        )

    return overrides, min(version, CURRENT_SCHEMA_VERSION)


def load_runtime_file(path: Path) -> tuple[dict[str, Any], int, bool]:
    """Load overrides from disk. Returns (overrides, version, migrated)."""
    if not path.exists():
        return {}, CURRENT_SCHEMA_VERSION, False
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as e:  # noqa: BLE001
        log.warning("Failed to read runtime overrides (%s); ignoring.", e)
        return {}, CURRENT_SCHEMA_VERSION, False

    if not isinstance(raw, dict):
        return {}, CURRENT_SCHEMA_VERSION, False

    original_version = _detect_version(raw)
    overrides, version = migrate_overrides(raw)
    migrated = original_version < version or (
        original_version == 0 and bool(overrides)
    )
    return overrides, version, migrated


def save_runtime_file(path: Path, version: int, overrides: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {SCHEMA_VERSION_KEY: version, OVERRIDES_KEY: overrides}
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
