"""Runtime config override schema versioning and migration."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable

import yaml

log = logging.getLogger("config_migration")

CURRENT_SCHEMA_VERSION = 1
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


MIGRATIONS: list[tuple[int, int, Callable[[dict[str, Any]], dict[str, Any]]]] = [
    (0, 1, migrate_v0_to_v1),
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
