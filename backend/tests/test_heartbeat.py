"""HA heartbeat pulse tests."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import pytest

from app.ha.heartbeat import HAHeartbeat
from app.observability.metrics import metrics


@pytest.fixture(autouse=True)
def _reset_metrics():
    metrics.heartbeat_pulses_total = 0
    metrics.heartbeat_failures = 0


@pytest.mark.asyncio
async def test_pulse_skipped_when_entity_unset():
    ha = MagicMock()
    hb = HAHeartbeat(ha)
    tz = ZoneInfo("UTC")
    assert await hb.pulse(None, site_tz=tz) is False
    assert await hb.pulse("", site_tz=tz) is False
    ha.call_service.assert_not_called()


@pytest.mark.asyncio
async def test_pulse_calls_input_datetime_set_datetime():
    ha = MagicMock()
    ha.call_service = AsyncMock()
    hb = HAHeartbeat(ha)
    ok = await hb.pulse(
        "input_datetime.solar_optimizer_heartbeat",
        site_tz=ZoneInfo("UTC"),
    )
    assert ok is True
    ha.call_service.assert_awaited_once()
    args, _kwargs = ha.call_service.await_args
    assert args[0] == "input_datetime"
    assert args[1] == "set_datetime"
    assert args[2]["entity_id"] == "input_datetime.solar_optimizer_heartbeat"
    assert "datetime" in args[2]
    assert hb.last_pulse_at is not None
    assert metrics.heartbeat_pulses_total == 1


@pytest.mark.asyncio
async def test_pulse_writes_site_local_wall_clock(monkeypatch):
    fixed = datetime(2026, 7, 8, 5, 27, 0, tzinfo=timezone.utc)
    monkeypatch.setattr("app.ha.heartbeat.utcnow", lambda: fixed)
    ha = MagicMock()
    ha.call_service = AsyncMock()
    hb = HAHeartbeat(ha)
    ok = await hb.pulse(
        "input_datetime.solar_optimizer_heartbeat",
        site_tz=ZoneInfo("Asia/Riyadh"),
    )
    assert ok is True
    args, _kwargs = ha.call_service.await_args
    assert args[2]["datetime"] == "2026-07-08 08:27:00"


@pytest.mark.asyncio
async def test_pulse_failure_increments_metric():
    from app.ha.client import HAError

    ha = MagicMock()
    ha.call_service = AsyncMock(side_effect=HAError("down"))
    hb = HAHeartbeat(ha)
    assert await hb.pulse("input_datetime.test", site_tz=ZoneInfo("UTC")) is False
    assert metrics.heartbeat_failures == 1
    assert hb.last_pulse_at is None
