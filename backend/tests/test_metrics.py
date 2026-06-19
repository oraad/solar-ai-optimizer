"""Prometheus metrics exposition."""

from __future__ import annotations

from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.metrics import metrics_router
from app.models import SystemStatus, utcnow


def test_metrics_prometheus_format():
    orch = MagicMock()
    orch.build_status.return_value = SystemStatus(
        ha_connected=True,
        telemetry_stale=False,
        last_updated=utcnow(),
    )
    app = FastAPI()
    app.state.orchestrator = orch
    app.include_router(metrics_router)
    res = TestClient(app).get("/metrics")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/plain")
    assert "solar_control_cycles_total" in res.text
    assert "solar_ha_connected" in res.text
