"""Regression tests for grid-stats 500 (no async — avoids event-loop fixture)."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from app.config import BatteryConfig, ReserveConfig
from app.grid.reactive import ReactiveGrid
from app.models import GridEvent, as_utc, utcnow
from app.storage import repo
from app.storage.db import close_db, init_db


def test_as_utc_normalizes_naive_sqlite_timestamps() -> None:
    from datetime import datetime, timezone

    naive = datetime(2026, 1, 1, 12, 0, 0)
    aware = as_utc(naive)
    assert aware.tzinfo == timezone.utc
    assert as_utc(utcnow()).tzinfo == timezone.utc


def test_compute_stats_with_sqlite_grid_events() -> None:
    """Regression: SQLite returns naive timestamps; stats must not crash."""

    async def _run() -> None:
        tmp = Path(tempfile.mkdtemp())
        db_url = "sqlite+aiosqlite:///" + str(tmp / "t.db").replace("\\", "/")
        await init_db(db_url)
        try:
            await repo.save_grid_event(GridEvent(ts=utcnow(), grid_present=True))
            grid = ReactiveGrid(BatteryConfig(), ReserveConfig())
            stats = await grid.compute_stats(live_present=True)
            assert stats.currently_present is True
            assert stats.last_seen is not None
        finally:
            await close_db()

    asyncio.run(_run())


def test_grid_stats_endpoint_fail_soft() -> None:
    """Endpoint returns default stats when compute_stats fails."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api.routes import router

    orch = MagicMock()
    orch.latest_grid_stats = None
    orch.collector.latest = None
    orch.reactive.compute_stats = AsyncMock(side_effect=RuntimeError("db down"))

    app = FastAPI()
    app.state.orchestrator = orch
    app.include_router(router)
    res = TestClient(app).get("/api/grid-stats")

    assert res.status_code == 200
    body = res.json()
    assert body["currently_present"] is None
    assert body["uptime_pct_24h"] == 0.0
