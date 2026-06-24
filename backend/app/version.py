"""Read the canonical release version from the repo-root VERSION file."""

from __future__ import annotations

from pathlib import Path

_VERSION_FILE = "VERSION"


def read_version() -> str:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / _VERSION_FILE
        if candidate.is_file():
            return candidate.read_text(encoding="utf-8").replace("\r", "").strip()
    raise RuntimeError("VERSION file not found")
