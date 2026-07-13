"""In-process liveness pulse tests."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.ha.heartbeat import HAHeartbeat
from app.observability.metrics import metrics


@pytest.fixture(autouse=True)
def _reset_metrics():
    metrics.heartbeat_pulses_total = 0
    metrics.heartbeat_failures = 0


def test_pulse_sets_last_pulse_at(monkeypatch):
    fixed = datetime(2026, 7, 8, 5, 27, 0, tzinfo=timezone.utc)
    monkeypatch.setattr("app.ha.heartbeat.utcnow", lambda: fixed)
    hb = HAHeartbeat()
    assert hb.pulse() is True
    assert hb.last_pulse_at == fixed
    assert metrics.heartbeat_pulses_total == 1


def test_pulse_does_not_call_home_assistant():
    hb = HAHeartbeat()
    assert hb.pulse() is True
    # No HA client is attached; pulse must succeed without external I/O.
    assert hb.last_pulse_at is not None
    assert metrics.heartbeat_failures == 0
