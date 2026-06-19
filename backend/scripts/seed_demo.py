"""Seed SQLite history and runtime config for documentation screenshots.

Usage (inside container):
    python -m scripts.seed_demo

Requires DEMO_MODE=true or a writable DATA_DIR. Restart the app after seeding
if it was already running so config overrides are reloaded.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

# Allow `python -m scripts.seed_demo` from /app.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config_migration import CURRENT_SCHEMA_VERSION, save_runtime_file
from app.demo import (
    demo_config_overrides,
    demo_decision,
    demo_execution,
    demo_shed_execution,
    historical_grid_events,
    historical_telemetry_series,
)
from app.storage import repo
from app.storage.db import close_db, init_db

log = logging.getLogger("seed_demo")


def _data_dir() -> Path:
    return Path(os.environ.get("DATA_DIR", "/app/data"))


def _runtime_path(data_dir: Path) -> Path:
    return data_dir / "config.runtime.yaml"


def write_demo_config(data_dir: Path) -> None:
    path = _runtime_path(data_dir)
    save_runtime_file(path, CURRENT_SCHEMA_VERSION, demo_config_overrides())
    log.info("Wrote demo config to %s", path)


async def seed_history() -> None:
    """Insert synthetic history rows (idempotent-ish: appends new rows)."""
    for t in historical_telemetry_series(days=7, interval_minutes=15):
        await repo.save_telemetry(t)

    for ev in historical_grid_events(days=7):
        await repo.save_grid_event(ev)

    # Decisions every 30 minutes over last 3 days.
    from app.models import utcnow
    from datetime import timedelta

    end = utcnow()
    t = end - timedelta(days=3)
    while t <= end:
        await repo.save_decision(demo_decision(t))
        await repo.save_execution(demo_execution(t))
        if t.hour % 6 == 0:
            await repo.save_shed_execution(demo_shed_execution(t))
        t += timedelta(minutes=30)

    log.info("Seeded telemetry, grid events, decisions, and executions.")


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    data_dir = _data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    db_url = os.environ.get(
        "DATABASE_URL", f"sqlite+aiosqlite:///{data_dir / 'solar.db'}"
    )
    await init_db(db_url)
    write_demo_config(data_dir)
    await seed_history()
    await close_db()
    print(
        "Demo data seeded. Restart the solar container if it is already running:\n"
        "  docker compose restart solar"
    )


if __name__ == "__main__":
    asyncio.run(main())
