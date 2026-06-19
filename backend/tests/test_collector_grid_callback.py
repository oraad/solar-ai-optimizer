"""Grid callback must not fire from sample() (avoids control_cycle deadlock)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.ingest.collector import Collector
from app.models import Telemetry, utcnow


@pytest.fixture
def collector():
    ha = MagicMock()
    adapter = MagicMock()
    adapter.read_telemetry = AsyncMock(
        return_value=Telemetry(
            ts=utcnow(),
            battery_soc=50.0,
            grid_present=True,
        )
    )
    adapter.telemetry_from_cache.return_value = Telemetry(
        ts=utcnow(),
        battery_soc=50.0,
        grid_present=True,
    )
    callback = AsyncMock()
    c = Collector(ha, adapter, "binary_sensor.grid", on_grid_change=callback)
    c._last_grid_present = False
    return c, callback, adapter


@pytest.mark.asyncio
async def test_sample_records_grid_without_callback(collector, monkeypatch):
    c, callback, _adapter = collector
    save_event = AsyncMock()
    save_telemetry = AsyncMock()
    monkeypatch.setattr("app.ingest.collector.repo.save_grid_event", save_event)
    monkeypatch.setattr("app.ingest.collector.repo.save_telemetry", save_telemetry)

    await c.sample()

    save_event.assert_awaited_once()
    callback.assert_not_awaited()


@pytest.mark.asyncio
async def test_stream_grid_change_invokes_callback(collector, monkeypatch):
    c, callback, _adapter = collector
    save_event = AsyncMock()
    monkeypatch.setattr("app.ingest.collector.repo.save_grid_event", save_event)

    await c._handle_grid_state(True, notify=True)

    save_event.assert_awaited_once()
    callback.assert_awaited_once_with(True)
