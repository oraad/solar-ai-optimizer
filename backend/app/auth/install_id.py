"""Stable install UUID for pairing / HA unique_id."""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

log = logging.getLogger("auth.install_id")

INSTALL_ID_FILENAME = "install_id"


def install_id_path(data_dir: Path | str) -> Path:
    return Path(data_dir) / INSTALL_ID_FILENAME


def get_or_create_install_id(data_dir: Path | str) -> str:
    """Return a stable UUID stored under DATA_DIR (created once)."""
    path = install_id_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        raw = path.read_text(encoding="utf-8").strip()
        try:
            return str(uuid.UUID(raw))
        except ValueError:
            log.warning("Invalid install_id in %s; regenerating", path)
    value = str(uuid.uuid4())
    path.write_text(f"{value}\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return value
