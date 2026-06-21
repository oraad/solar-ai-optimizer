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
CONFIG_YAML = ROOT / "config.yaml"
PACKAGE_JSON = ROOT / "frontend" / "package.json"


def read_canonical_version() -> str:
    if not VERSION_FILE.is_file():
        raise SystemExit(f"Missing {VERSION_FILE}")
    version = VERSION_FILE.read_text(encoding="utf-8").strip()
    if not version:
        raise SystemExit(f"{VERSION_FILE} is empty")
    return version


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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify derived files match VERSION; do not write",
    )
    args = parser.parse_args()

    expected = read_canonical_version()

    if args.check:
        ok = True
        ok &= check_version("config.yaml", CONFIG_YAML, read_config_yaml_version(), expected)
        ok &= check_version(
            "frontend/package.json", PACKAGE_JSON, read_package_json_version(), expected
        )
        if not ok:
            return 1
        print(f"All version files match {expected}")
        return 0

    changed = False
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
