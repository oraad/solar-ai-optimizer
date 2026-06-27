#!/usr/bin/env python3
"""Sync or verify derived version fields from the root VERSION file."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = ROOT / "VERSION"
CONFIG_YAML = ROOT / "solar_ai_optimizer" / "config.yaml"
ADDON_ICON = ROOT / "solar_ai_optimizer" / "icon.png"
ADDON_LOGO = ROOT / "solar_ai_optimizer" / "logo.png"
PACKAGE_JSON = ROOT / "frontend" / "package.json"


def parse_version_text(raw: str) -> str:
    """Return the semver string, tolerating trailing whitespace."""
    return raw.replace("\r", "").strip()


def read_version_bytes() -> bytes:
    if not VERSION_FILE.is_file():
        raise SystemExit(f"Missing {VERSION_FILE}")
    return VERSION_FILE.read_bytes()


def canonical_version_bytes(version: str) -> bytes:
    return f"{version}\n".encode("utf-8")


def read_canonical_version() -> str:
    version = parse_version_text(read_version_bytes().decode("utf-8"))
    if not version:
        raise SystemExit(f"{VERSION_FILE} is empty")
    return version


def verify_version_lf() -> bool:
    raw = read_version_bytes()
    if b"\r" in raw:
        print(f"{VERSION_FILE} contains CR bytes; run sync-version.py to normalize", file=sys.stderr)
        return False
    expected = canonical_version_bytes(read_canonical_version())
    if raw != expected:
        print(
            f"{VERSION_FILE} must be exactly '<version>\\n' (LF only); run sync-version.py to normalize",
            file=sys.stderr,
        )
        return False
    return True


def write_version_file(version: str) -> None:
    VERSION_FILE.write_bytes(canonical_version_bytes(version))


def read_config_yaml_version() -> str:
    text = CONFIG_YAML.read_text(encoding="utf-8")
    match = re.search(r'^version:\s*"(?P<v>[^"]+)"\s*$', text, re.MULTILINE)
    if not match:
        raise SystemExit(f'Could not find version: "..." in {CONFIG_YAML}')
    return match.group("v")


def read_package_json_version() -> str:
    data = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))
    version = data.get("version")
    if not isinstance(version, str) or not version:
        raise SystemExit(f'Missing "version" in {PACKAGE_JSON}')
    return version


def write_config_yaml_version(version: str) -> None:
    text = CONFIG_YAML.read_text(encoding="utf-8")
    updated, count = re.subn(
        r'^version:\s*"[^"]+"\s*$',
        f'version: "{version}"',
        text,
        count=1,
        flags=re.MULTILINE,
    )
    if count != 1:
        raise SystemExit(f'Could not update version in {CONFIG_YAML}')
    CONFIG_YAML.write_text(updated, encoding="utf-8", newline="\n")


def write_package_json_version(version: str) -> None:
    data = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))
    data["version"] = version
    PACKAGE_JSON.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def check_version(label: str, path: Path, actual: str, expected: str) -> bool:
    if actual == expected:
        return True
    print(f"{label} drift: {path} has {actual!r}, expected {expected!r}", file=sys.stderr)
    return False


def check_addon_store_assets() -> bool:
    ok = True
    for label, path in (("icon.png", ADDON_ICON), ("logo.png", ADDON_LOGO)):
        if not path.is_file():
            print(f"Missing HA app store asset: {path}", file=sys.stderr)
            ok = False
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify VERSION (LF-only) and derived files; do not write",
    )
    args = parser.parse_args()

    if args.check:
        ok = verify_version_lf()
        expected = read_canonical_version()
        ok &= check_version("config.yaml", CONFIG_YAML, read_config_yaml_version(), expected)
        ok &= check_version(
            "frontend/package.json", PACKAGE_JSON, read_package_json_version(), expected
        )
        ok &= check_addon_store_assets()
        if not ok:
            return 1
        print(f"All version files match {expected}")
        return 0

    expected = read_canonical_version()
    raw_before = read_version_bytes()
    write_version_file(expected)
    changed = raw_before != canonical_version_bytes(expected)
    if changed:
        print(f"Normalized {VERSION_FILE} to LF")

    if read_config_yaml_version() != expected:
        write_config_yaml_version(expected)
        print(f"Updated {CONFIG_YAML} -> {expected}")
        changed = True
    if read_package_json_version() != expected:
        write_package_json_version(expected)
        print(f"Updated {PACKAGE_JSON} -> {expected}")
        changed = True
    if not changed:
        print(f"Already in sync at {expected}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
