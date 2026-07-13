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
    """Write runtime state atomically (temp file + rename) and lock it down to 0600.

    Avoids readers ever observing a partially-written file, and avoids leaking
    operator overrides/paused state to other local users.
    """
    p = _path(data_dir)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
        tmp.replace(p)
        try:
            p.chmod(0o600)
        except OSError:
            pass
    except Exception as e:  # noqa: BLE001
        log.warning("Failed to save runtime state: %s", e)
