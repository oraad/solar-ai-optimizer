"""Persist operator runtime flags (paused, shadow, overrides) across restarts."""

from __future__ import annotations

import json
import logging
from pathlib import Path

log = logging.getLogger("runtime_state")


def _path(data_dir: str) -> Path:
    return Path(data_dir) / "runtime_state.json"


def load(data_dir: str) -> dict:
    p = _path(data_dir)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        log.warning("Failed to load runtime state: %s", e)
        return {}


def save(data_dir: str, state: dict) -> None:
    p = _path(data_dir)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        log.warning("Failed to save runtime state: %s", e)
