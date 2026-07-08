#!/usr/bin/env python3
"""Extract a version section from CHANGELOG.md for GitHub release notes."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


def _app_heading(version: str) -> str:
    return rf"^## \[{re.escape(version)}\][^\n]*\n"


def _integration_heading(version: str) -> str:
    return rf"^## \[integration {re.escape(version)}\][^\n]*\n"


def excerpt(changelog: str, version: str, *, kind: str = "app") -> str | None:
    """Return the body under a release heading or None if not found."""
    if kind == "integration":
        pattern = re.compile(
            _integration_heading(version) + r"(.*?)(?=^## \[|\Z)",
            re.MULTILINE | re.DOTALL,
        )
    else:
        pattern = re.compile(
            _app_heading(version) + r"(.*?)(?=^## \[|\Z)",
            re.MULTILINE | re.DOTALL,
        )
    match = pattern.search(changelog)
    if not match:
        return None
    body = match.group(1).strip()
    if kind == "app" and body:
        app_only = re.search(
            r"^### App\s*\n(.*?)(?=^### |\Z)",
            body,
            re.MULTILINE | re.DOTALL,
        )
        if app_only:
            body = app_only.group(1).strip()
    if kind == "integration" and body:
        integration_only = re.search(
            r"^### Integration\s*\n(.*?)(?=^### |\Z)",
            body,
            re.MULTILINE | re.DOTALL,
        )
        if integration_only:
            body = integration_only.group(1).strip()
    return body or None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--changelog",
        type=Path,
        default=Path("CHANGELOG.md"),
        help="Path to CHANGELOG.md",
    )
    parser.add_argument(
        "--version",
        required=True,
        help="Release version without leading v (e.g. 0.5.1)",
    )
    parser.add_argument(
        "--kind",
        choices=("app", "integration"),
        default="app",
        help="Release track: app (## [X.Y.Z]) or integration (## [integration X.Y.Z])",
    )
    args = parser.parse_args()

    text = args.changelog.read_text(encoding="utf-8")
    section = excerpt(text, args.version, kind=args.kind)
    if section is None:
        return 1
    sys.stdout.write(section)
    if not section.endswith("\n"):
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
