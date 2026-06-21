"""Version file and sync script tests."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from app import __version__
from app.version import read_version


def _repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "VERSION").is_file():
            return parent
    raise RuntimeError("VERSION file not found")


ROOT = _repo_root()


def test_read_version_matches_root_file():
    expected = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    assert read_version() == expected
    assert __version__ == expected


def test_sync_version_check_passes():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "sync-version.py"), "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
