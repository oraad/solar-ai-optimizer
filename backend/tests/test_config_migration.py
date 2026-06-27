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
    assert cfg.site.latitude == -33.9
    raw = yaml.safe_load(runtime.read_text(encoding="utf-8"))
    assert raw["schema_version"] == CURRENT_SCHEMA_VERSION
    assert raw["overrides"]["site"]["latitude"] == -33.9
    assert "latitude" not in raw["overrides"].get("forecast", {})


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
    store.update({"site": {"latitude": -34.0}})
    raw = yaml.safe_load(runtime.read_text(encoding="utf-8"))
    assert raw["schema_version"] == CURRENT_SCHEMA_VERSION
    assert raw["overrides"]["site"]["latitude"] == -34.0


def test_migrate_overrides_identity():
    overrides, version = migrate_overrides({"reserve": {"critical_load_w": 500}})
    assert version == CURRENT_SCHEMA_VERSION
    assert overrides["reserve"]["critical_load_w"] == 500


def test_migrate_v1_to_v2_max_charge_a():
    overrides, version = migrate_overrides(
        {
            "schema_version": 1,
            "overrides": {
                "battery": {"max_charge_a": 100.0, "max_grid_charge_a": 60.0},
                "inverter": {
                    "write": {"work_mode": "select.deye_work_mode"},
                    "work_modes": {"grid_first": "Grid First"},
                },
            },
        }
    )
    assert version == CURRENT_SCHEMA_VERSION
    assert overrides["grid_charge"]["max_grid_charge_a"] == 100.0
    assert "max_grid_charge_a" not in overrides.get("battery", {})
    assert "max_charge_a" not in overrides.get("battery", {})
    assert "work_mode" not in overrides["inverter"]["write"]
    assert "work_modes" not in overrides["inverter"]


def test_migrate_v2_to_v3_moves_max_to_grid_charge():
    overrides, version = migrate_overrides(
        {
            "schema_version": 2,
            "overrides": {
                "battery": {"max_grid_charge_a": 80.0, "capacity_kwh": 10.0},
                "grid_charge": {"min_grid_charge_a": 5.0},
            },
        }
    )
    assert version == CURRENT_SCHEMA_VERSION
    assert overrides["grid_charge"]["max_grid_charge_a"] == 80.0
    assert overrides["grid_charge"]["min_grid_charge_a"] == 5.0
    assert "max_grid_charge_a" not in overrides["battery"]


def test_migrate_v3_to_v4_moves_forecast_timezone():
    overrides, version = migrate_overrides(
        {
            "schema_version": 3,
            "overrides": {
                "forecast": {"timezone": "Africa/Johannesburg", "latitude": -33.9},
            },
        }
    )
    assert version == CURRENT_SCHEMA_VERSION
    assert overrides["site"]["timezone"] == "Africa/Johannesburg"
    assert overrides["site"]["latitude"] == -33.9
    assert "timezone" not in overrides["forecast"]
    assert "latitude" not in overrides["forecast"]


def test_migrate_v4_to_v5_moves_forecast_coordinates():
    overrides, version = migrate_overrides(
        {
            "schema_version": 4,
            "overrides": {
                "forecast": {"latitude": -33.9, "longitude": 18.4, "provider": "open-meteo"},
            },
        }
    )
    assert version == CURRENT_SCHEMA_VERSION
    assert overrides["site"]["latitude"] == -33.9
    assert overrides["site"]["longitude"] == 18.4
    assert "latitude" not in overrides["forecast"]
    assert "longitude" not in overrides["forecast"]
    assert overrides["forecast"]["provider"] == "open-meteo"


def test_migrate_v4_to_v5_keeps_existing_site_coordinates():
    overrides, version = migrate_overrides(
        {
            "schema_version": 4,
            "overrides": {
                "site": {"latitude": -34.0, "longitude": 19.0},
                "forecast": {"latitude": -33.9, "longitude": 18.4},
            },
        }
    )
    assert version == CURRENT_SCHEMA_VERSION
    assert overrides["site"]["latitude"] == -34.0
    assert overrides["site"]["longitude"] == 19.0


def test_migrate_v5_to_v6_removes_factor_order():
    overrides, version = migrate_overrides(
        {
            "schema_version": 5,
            "overrides": {
                "grid_charge": {
                    "factor_order": ["soc_gap", "grid_window"],
                    "max_grid_charge_a": 60.0,
                },
            },
        }
    )
    assert version == CURRENT_SCHEMA_VERSION
    assert "factor_order" not in overrides["grid_charge"]
    assert overrides["grid_charge"]["max_grid_charge_a"] == 60.0
