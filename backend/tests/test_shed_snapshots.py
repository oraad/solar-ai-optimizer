"""Shed snapshot store persistence."""

from __future__ import annotations

import json
from pathlib import Path

from app.shed_snapshots import EntitySnapshot, ShedSnapshotStore


def test_capture_and_clear(tmp_path: Path):
    store = ShedSnapshotStore(str(tmp_path))
    store.capture(
        "switch.pool",
        was_on=True,
        companions={
            "climate.pool": EntitySnapshot(state="cool", attributes={"temperature": 22}),
        },
    )
    snap = store.get("switch.pool")
    assert snap is not None
    assert snap.was_on is True
    assert "climate.pool" in snap.companions

    path = tmp_path / "shed_snapshots.json"
    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert "switch.pool" in data

    store.clear("switch.pool")
    assert store.get("switch.pool") is None


def test_prune_removes_unknown_entities(tmp_path: Path):
    store = ShedSnapshotStore(str(tmp_path))
    store.capture("switch.old", was_on=True)
    store.capture("switch.keep", was_on=False)
    store.prune({"switch.keep"})
    assert store.get("switch.old") is None
    assert store.get("switch.keep") is not None
