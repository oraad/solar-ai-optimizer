"""Persistent, UI-editable configuration.

Effective config = base YAML (config/config.yaml, read-only) deep-merged with a
runtime overrides file kept in the writable data dir. UI edits are saved as
overrides so the shipped base file is never mutated and upgrades stay clean.
"""

from __future__ import annotations

import copy
import logging
from pathlib import Path
from typing import Any

import yaml

from .config import AppConfig, load_app_config
from .config_migration import (
    CURRENT_SCHEMA_VERSION,
    load_runtime_file,
    save_runtime_file,
)

log = logging.getLogger("config_store")


def deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge `override` into a copy of `base` (override wins)."""
    out = copy.deepcopy(base)
    for key, val in (override or {}).items():
        if key in out and isinstance(out[key], dict) and isinstance(val, dict):
            out[key] = deep_merge(out[key], val)
        else:
            out[key] = copy.deepcopy(val)
    return out


class ConfigStore:
    def __init__(self, base_path: str, runtime_path: str) -> None:
        self._base_path = Path(base_path)
        self._runtime_path = Path(runtime_path)

    def _base_dict(self) -> dict[str, Any]:
        if not self._base_path.exists():
            return {}
        return yaml.safe_load(self._base_path.read_text(encoding="utf-8")) or {}

    def _overrides(self) -> dict[str, Any]:
        overrides, version, migrated = load_runtime_file(self._runtime_path)
        if migrated:
            log.info(
                "Runtime config migrated to schema v%s; rewriting %s",
                version,
                self._runtime_path,
            )
            save_runtime_file(self._runtime_path, version, overrides)
        return overrides

    def effective_dict(self) -> dict[str, Any]:
        return deep_merge(self._base_dict(), self._overrides())

    def load(self) -> AppConfig:
        """Return the validated effective config."""
        try:
            return AppConfig.model_validate(self.effective_dict())
        except Exception as e:  # noqa: BLE001
            log.error("Invalid effective config (%s); falling back to base.", e)
            return load_app_config(self._base_path)

    def update(self, patch: dict[str, Any]) -> AppConfig:
        """Deep-merge `patch` into overrides, validate, persist, and return config."""
        new_overrides = deep_merge(self._overrides(), patch)
        candidate = deep_merge(self._base_dict(), new_overrides)
        cfg = AppConfig.model_validate(candidate)  # raises on invalid
        save_runtime_file(self._runtime_path, CURRENT_SCHEMA_VERSION, new_overrides)
        log.info("Configuration updated and persisted to %s", self._runtime_path)
        return cfg

    def reset(self) -> AppConfig:
        """Discard all overrides (revert to the base YAML)."""
        if self._runtime_path.exists():
            self._runtime_path.unlink()
        log.info("Configuration overrides cleared.")
        return self.load()
