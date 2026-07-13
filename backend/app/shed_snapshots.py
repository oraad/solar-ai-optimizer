"""Persist pre-shed power + companion entity snapshots across restarts."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .models import utcnow

log = logging.getLogger("shed_snapshots")


class EntitySnapshot(BaseModel):
    state: str
    attributes: dict[str, Any] = Field(default_factory=dict)


class PowerEntitySnapshot(BaseModel):
    was_on: bool
    companions: dict[str, EntitySnapshot] = Field(default_factory=dict)
    captured_at: datetime = Field(default_factory=utcnow)


class ShedSnapshotStore:
    def __init__(self, data_dir: str) -> None:
        self._path = Path(data_dir) / "shed_snapshots.json"
        self._snapshots: dict[str, PowerEntitySnapshot] = {}
        self.load()

    def load(self) -> None:
        if not self._path.exists():
            self._snapshots = {}
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            self._snapshots = {
                k: PowerEntitySnapshot.model_validate(v)
                for k, v in (raw or {}).items()
            }
        except Exception as e:  # noqa: BLE001
            log.warning("Failed to load shed snapshots: %s", e)
            self._snapshots = {}

    def save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                k: v.model_dump(mode="json") for k, v in self._snapshots.items()
            }
            tmp = self._path.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            tmp.replace(self._path)
            try:
                self._path.chmod(0o600)
            except OSError:
                pass
        except Exception as e:  # noqa: BLE001
            log.warning("Failed to save shed snapshots: %s", e)

    def get(self, power_entity: str) -> PowerEntitySnapshot | None:
        return self._snapshots.get(power_entity)

    def capture(
        self,
        power_entity: str,
        *,
        was_on: bool,
        companions: dict[str, EntitySnapshot] | None = None,
    ) -> None:
        # Episode capture-once: do not overwrite a pending snapshot.
        if power_entity in self._snapshots:
            return
        self._snapshots[power_entity] = PowerEntitySnapshot(
            was_on=was_on,
            companions=companions or {},
            captured_at=utcnow(),
        )
        self.save()

    def clear(self, power_entity: str) -> None:
        if power_entity in self._snapshots:
            del self._snapshots[power_entity]
            self.save()

    def prune(self, known_entities: set[str]) -> None:
        stale = [k for k in self._snapshots if k not in known_entities]
        if not stale:
            return
        for k in stale:
            del self._snapshots[k]
        self.save()

    def list_all(self) -> dict[str, PowerEntitySnapshot]:
        return dict(self._snapshots)
