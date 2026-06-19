"""Config runtime override schema migration."""

from __future__ import annotations

import yaml

from app.config_migration import (
    CURRENT_SCHEMA_VERSION,
    load_runtime_file,
    migrate_overrides,
    save_runtime_file,
)
from app.config_store import ConfigStore


def test_legacy_flat_overrides_migrate_to_v1(tmp_path):
    base = tmp_path / "base.yaml"
    base.write_text("battery:\n  capacity_kwh: 10\n", encoding="utf-8")
    runtime = tmp_path / "config.runtime.yaml"
    runtime.write_text(
        yaml.safe_dump({"forecast": {"latitude": -33.9}}),
        encoding="utf-8",
    )
    store = ConfigStore(str(base), str(runtime))
    cfg = store.load()
    assert cfg.forecast.latitude == -33.9
    raw = yaml.safe_load(runtime.read_text(encoding="utf-8"))
    assert raw["schema_version"] == CURRENT_SCHEMA_VERSION
    assert raw["overrides"]["forecast"]["latitude"] == -33.9


def test_v1_wrapped_file_loads_without_rewrite(tmp_path):
    runtime = tmp_path / "config.runtime.yaml"
    save_runtime_file(runtime, 1, {"battery": {"capacity_kwh": 12.0}})
    mtime = runtime.stat().st_mtime
    overrides, version, migrated = load_runtime_file(runtime)
    assert version == CURRENT_SCHEMA_VERSION
    assert overrides["battery"]["capacity_kwh"] == 12.0
    assert runtime.stat().st_mtime == mtime


def test_config_store_update_writes_v1_format(tmp_path):
    base = tmp_path / "base.yaml"
    base.write_text("battery:\n  capacity_kwh: 10\n", encoding="utf-8")
    runtime = tmp_path / "runtime.yaml"
    store = ConfigStore(str(base), str(runtime))
    store.update({"forecast": {"latitude": -34.0}})
    raw = yaml.safe_load(runtime.read_text(encoding="utf-8"))
    assert raw["schema_version"] == CURRENT_SCHEMA_VERSION
    assert raw["overrides"]["forecast"]["latitude"] == -34.0


def test_migrate_overrides_identity():
    overrides, version = migrate_overrides({"reserve": {"critical_load_w": 500}})
    assert version == CURRENT_SCHEMA_VERSION
    assert overrides["reserve"]["critical_load_w"] == 500
