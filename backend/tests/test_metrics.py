"""Prometheus metrics exposition."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.api.metrics import metrics_router
from app.models import SystemStatus, utcnow
from tests.conftest_auth import api_with_router, clear_auth_env


def test_metrics_prometheus_format(monkeypatch):
    clear_auth_env(monkeypatch)
    orch = MagicMock()
    orch.build_status.return_value = SystemStatus(
        ha_connected=True,
        telemetry_stale=False,
        last_updated=utcnow(),
    )
    res = api_with_router(metrics_router, orch).get("/metrics")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/plain")
    assert "solar_control_cycles_total" in res.text
    assert "solar_ha_connected" in res.text
