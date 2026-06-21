"""Grid stats use separate 24h vs 7d baselines and live presence for last_seen."""

from __future__ import annotations

from datetime import timedelta

import pytest

from app.config import BatteryConfig, ReserveConfig
from app.grid.reactive import ReactiveGrid
from app.models import GridEvent, utcnow


@pytest.mark.asyncio
async def test_uptime_24h_uses_24h_baseline(monkeypatch: pytest.MonkeyPatch):
    now = utcnow()
    events = [
        GridEvent(ts=now - timedelta(days=3), grid_present=True),
        GridEvent(ts=now - timedelta(hours=12), grid_present=False),
        GridEvent(ts=now - timedelta(hours=6), grid_present=True),
    ]

    async def fake_events(since):
        return [e for e in events if e.ts >= since]

    async def fake_last():
        return events[-1]

    monkeypatch.setattr("app.grid.reactive.repo.get_grid_events_since", fake_events)
    monkeypatch.setattr("app.grid.reactive.repo.get_last_grid_event", fake_last)

    grid = ReactiveGrid(BatteryConfig(), ReserveConfig())
    stats = await grid.compute_stats(now=now, live_present=True)

    assert stats.uptime_pct_24h != stats.uptime_pct_7d
    assert stats.currently_present is True
    assert stats.last_seen == now