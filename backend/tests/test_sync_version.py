"""Tests for scripts/sync-version.py HA manifest rules."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve()
for _parent in ROOT.parents:
    if (_parent / "VERSION").is_file() and (_parent / "scripts" / "sync-version.py").is_file():
        ROOT = _parent
        break
else:
    raise RuntimeError("Repository root not found")
SCRIPT = ROOT / "scripts" / "sync-version.py"

_spec = importlib.util.spec_from_file_location("sync_version", SCRIPT)
assert _spec and _spec.loader
sv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sv)


def _write_fixture(
    root: Path,
    version: str,
    manifest: str,
    *,
    package: str | None = None,
    integration_version: str | None = None,
    integration_manifest: str | None = None,
) -> None:
    (root / "VERSION").write_text(f"{version}\n", encoding="utf-8", newline="\n")
    integration = integration_version if integration_version is not None else version
    integration_manifest_version = (
        integration_manifest if integration_manifest is not None else integration
    )
    (root / "INTEGRATION_VERSION").write_text(
        f"{integration}\n", encoding="utf-8", newline="\n"
    )
    addon_dir = root / "solar_ai_optimizer"
    addon_dir.mkdir(parents=True, exist_ok=True)
    config = f'name: "Test"\nversion: "{manifest}"\nslug: test\n'
    (addon_dir / "config.yaml").write_text(config, encoding="utf-8", newline="\n")
    (addon_dir / "icon.png").write_bytes(b"png")
    (addon_dir / "logo.png").write_bytes(b"png")
    frontend = root / "frontend"
    frontend.mkdir(parents=True, exist_ok=True)
    pkg_version = package if package is not None else version
    (frontend / "package.json").write_text(
        json.dumps({"version": pkg_version}) + "\n",
        encoding="utf-8",
    )
    integration_dir = root / "custom_components" / "solar_ai_optimizer"
    integration_dir.mkdir(parents=True, exist_ok=True)
    (integration_dir / "manifest.json").write_text(
        json.dumps(
            {"domain": "solar_ai_optimizer", "version": integration_manifest_version}
        )
        + "\n",
        encoding="utf-8",
    )


def test_is_prerelease():
    assert sv.is_prerelease("0.6.10-beta.2") is True
    assert sv.is_prerelease("0.6.10") is False


def test_check_ha_manifest_prerelease_passes():
    assert sv.check_ha_manifest_version(
        "0.6.10-beta.2", "0.6.9", Path("config.yaml")
    )


def test_check_ha_manifest_prerelease_rejects_matching_beta():
    assert not sv.check_ha_manifest_version(
        "0.6.10-beta.2", "0.6.10-beta.2", Path("config.yaml")
    )


def test_check_ha_manifest_prerelease_rejects_prerelease_manifest():
    assert not sv.check_ha_manifest_version(
        "0.6.10-beta.2", "0.6.10-beta.1", Path("config.yaml")
    )


def test_sync_preserves_stable_manifest_on_prerelease(tmp_path: Path):
    _write_fixture(tmp_path, "0.6.10-beta.2", "0.6.9", integration_version="0.1.0-beta.1")
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    assert sv.read_config_yaml_version(tmp_path / "solar_ai_optimizer" / "config.yaml") == "0.6.9"
    assert sv.read_package_json_version(tmp_path / "frontend" / "package.json") == "0.6.10-beta.2"
    assert (
        sv.read_integration_manifest_version(
            tmp_path / "custom_components" / "solar_ai_optimizer" / "manifest.json"
        )
        == "0.1.0-beta.1"
    )


def test_sync_bumps_manifest_on_stable(tmp_path: Path):
    _write_fixture(
        tmp_path,
        "0.6.10",
        "0.6.9",
        integration_version="0.1.0",
        integration_manifest="0.0.9",
    )
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    assert sv.read_config_yaml_version(tmp_path / "solar_ai_optimizer" / "config.yaml") == "0.6.10"
    assert (
        sv.read_integration_manifest_version(
            tmp_path / "custom_components" / "solar_ai_optimizer" / "manifest.json"
        )
        == "0.1.0"
    )


def test_sync_integration_only(tmp_path: Path):
    _write_fixture(
        tmp_path,
        "0.6.10-beta.3",
        "0.6.9",
        integration_version="0.1.1",
        integration_manifest="0.1.0",
    )
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(tmp_path), "--integration-only"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    assert sv.read_config_yaml_version(tmp_path / "solar_ai_optimizer" / "config.yaml") == "0.6.9"
    assert sv.read_package_json_version(tmp_path / "frontend" / "package.json") == "0.6.10-beta.3"
    assert (
        sv.read_integration_manifest_version(
            tmp_path / "custom_components" / "solar_ai_optimizer" / "manifest.json"
        )
        == "0.1.1"
    )


def test_check_passes_for_repo_state():
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
