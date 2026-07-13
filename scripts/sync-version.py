#!/usr/bin/env python3
"""Sync or verify derived version fields from VERSION."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_DEFAULT_ROOT = Path(__file__).resolve().parents[1]


def is_prerelease(version: str) -> bool:
    cleaned = version.lstrip("vV").strip().split("+", 1)[0]
    return "-" in cleaned


def parse_numeric_triple(version: str) -> tuple[int, int, int]:
    cleaned = version.lstrip("vV").strip().split("-", 1)[0].split("+", 1)[0]
    match = re.match(r"^(\d+)(?:\.(\d+))?(?:\.(\d+))?", cleaned)
    if not match:
        return (0, 0, 0)
    return tuple(int(part or 0) for part in match.groups())


def paths_for_root(root: Path) -> dict[str, Path]:
    return {
        "version": root / "VERSION",
        "config": root / "solar_ai_optimizer" / "config.yaml",
        "icon": root / "solar_ai_optimizer" / "icon.png",
        "logo": root / "solar_ai_optimizer" / "logo.png",
        "changelog": root / "CHANGELOG.md",
        "addon_changelog": root / "solar_ai_optimizer" / "CHANGELOG.md",
        "package": root / "frontend" / "package.json",
    }


def parse_version_text(raw: str) -> str:
    return raw.replace("\r", "").strip()


def read_version_bytes(version_file: Path) -> bytes:
    if not version_file.is_file():
        raise SystemExit(f"Missing {version_file}")
    return version_file.read_bytes()


def canonical_version_bytes(version: str) -> bytes:
    return f"{version}\n".encode("utf-8")


def read_canonical_version(version_file: Path) -> str:
    version = parse_version_text(read_version_bytes(version_file).decode("utf-8"))
    if not version:
        raise SystemExit(f"{version_file} is empty")
    return version


def verify_version_lf(version_file: Path) -> bool:
    raw = read_version_bytes(version_file)
    if b"\r" in raw:
        print(f"{version_file} contains CR bytes; run sync-version.py to normalize", file=sys.stderr)
        return False
    expected = canonical_version_bytes(read_canonical_version(version_file))
    if raw != expected:
        print(
            f"{version_file} must be exactly '<version>\\n' (LF only); run sync-version.py to normalize",
            file=sys.stderr,
        )
        return False
    return True


def write_version_file(version_file: Path, version: str) -> None:
    version_file.write_bytes(canonical_version_bytes(version))


def read_config_yaml_version(config_yaml: Path) -> str:
    text = config_yaml.read_text(encoding="utf-8")
    match = re.search(r'^version:\s*"(?P<v>[^"]+)"\s*$', text, re.MULTILINE)
    if not match:
        raise SystemExit(f'Could not find version: "..." in {config_yaml}')
    return match.group("v")


def read_package_json_version(package_json: Path) -> str:
    data = json.loads(package_json.read_text(encoding="utf-8"))
    version = data.get("version")
    if not isinstance(version, str) or not version:
        raise SystemExit(f'Missing "version" in {package_json}')
    return version


def write_config_yaml_version(config_yaml: Path, version: str) -> None:
    text = config_yaml.read_text(encoding="utf-8")
    updated, count = re.subn(
        r'^version:\s*"[^"]+"\s*$',
        f'version: "{version}"',
        text,
        count=1,
        flags=re.MULTILINE,
    )
    if count != 1:
        raise SystemExit(f'Could not update version in {config_yaml}')
    config_yaml.write_text(updated, encoding="utf-8", newline="\n")


def write_package_json_version(package_json: Path, version: str) -> None:
    data = json.loads(package_json.read_text(encoding="utf-8"))
    data["version"] = version
    package_json.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def check_version(label: str, path: Path, actual: str, expected: str) -> bool:
    if actual == expected:
        return True
    print(f"{label} drift: {path} has {actual!r}, expected {expected!r}", file=sys.stderr)
    return False


def check_ha_manifest_version(version: str, manifest_version: str, config_path: Path) -> bool:
    if is_prerelease(version):
        if manifest_version == version:
            print(
                f"HA manifest must not match prerelease VERSION during beta: "
                f"{config_path} has {manifest_version!r}",
                file=sys.stderr,
            )
            return False
        if is_prerelease(manifest_version):
            print(
                f"HA manifest must be stable during prerelease VERSION: "
                f"{config_path} has {manifest_version!r}",
                file=sys.stderr,
            )
            return False
        if parse_numeric_triple(manifest_version) > parse_numeric_triple(version):
            print(
                f"HA manifest version must not exceed VERSION base: "
                f"{config_path} has {manifest_version!r}, VERSION is {version!r}",
                file=sys.stderr,
            )
            return False
        return True
    return manifest_version == version


def check_addon_store_assets(icon: Path, logo: Path) -> bool:
    ok = True
    for label, path in (("icon.png", icon), ("logo.png", logo)):
        if not path.is_file():
            print(f"Missing HA app store asset: {path}", file=sys.stderr)
            ok = False
    return ok


def check_addon_changelog(root_changelog: Path, addon_changelog: Path) -> bool:
    if not root_changelog.is_file():
        print(f"Missing root changelog: {root_changelog}", file=sys.stderr)
        return False
    if not addon_changelog.is_file():
        print(
            f"Missing HA app store changelog: {addon_changelog}; run sync-version.py",
            file=sys.stderr,
        )
        return False
    root_bytes = root_changelog.read_bytes()
    addon_bytes = addon_changelog.read_bytes()
    if root_bytes != addon_bytes:
        print(
            f"HA app store changelog drift: {addon_changelog} differs from {root_changelog}; "
            "run sync-version.py",
            file=sys.stderr,
        )
        return False
    return True


def sync_addon_changelog(root_changelog: Path, addon_changelog: Path) -> bool:
    if not root_changelog.is_file():
        raise SystemExit(f"Missing {root_changelog}")
    root_bytes = root_changelog.read_bytes()
    if addon_changelog.is_file() and addon_changelog.read_bytes() == root_bytes:
        return False
    addon_changelog.parent.mkdir(parents=True, exist_ok=True)
    addon_changelog.write_bytes(root_bytes)
    print(f"Updated {addon_changelog}")
    return True


def sync_app_versions(paths: dict[str, Path], expected: str) -> bool:
    version_file = paths["version"]
    config_yaml = paths["config"]
    package_json = paths["package"]

    raw_before = read_version_bytes(version_file)
    write_version_file(version_file, expected)
    changed = raw_before != canonical_version_bytes(expected)
    if changed:
        print(f"Normalized {version_file} to LF")

    if read_package_json_version(package_json) != expected:
        write_package_json_version(package_json, expected)
        print(f"Updated {package_json} -> {expected}")
        changed = True

    if is_prerelease(expected):
        manifest = read_config_yaml_version(config_yaml)
        if manifest == expected:
            print(
                f"Skipped {config_yaml} (prerelease VERSION; HA manifest stays at {manifest})",
                file=sys.stderr,
            )
        else:
            print(f"Preserved HA manifest at {manifest} (prerelease VERSION {expected})")
    elif read_config_yaml_version(config_yaml) != expected:
        write_config_yaml_version(config_yaml, expected)
        print(f"Updated {config_yaml} -> {expected}")
        changed = True

    if sync_addon_changelog(paths["changelog"], paths["addon_changelog"]):
        changed = True

    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify VERSION (LF-only) and derived files; do not write",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=_DEFAULT_ROOT,
        help="Repository root (default: parent of scripts/)",
    )
    args = parser.parse_args()

    paths = paths_for_root(args.root.resolve())
    version_file = paths["version"]
    config_yaml = paths["config"]
    package_json = paths["package"]

    if args.check:
        ok = verify_version_lf(version_file)
        expected = read_canonical_version(version_file)
        manifest = read_config_yaml_version(config_yaml)
        ok &= check_ha_manifest_version(expected, manifest, config_yaml)
        ok &= check_version(
            "frontend/package.json", package_json, read_package_json_version(package_json), expected
        )
        ok &= check_addon_store_assets(paths["icon"], paths["logo"])
        ok &= check_addon_changelog(paths["changelog"], paths["addon_changelog"])
        if not ok:
            return 1
        print(f"App version {expected}")
        return 0

    expected = read_canonical_version(version_file)
    changed = sync_app_versions(paths, expected)
    if not changed:
        print(f"Already in sync at {expected}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
