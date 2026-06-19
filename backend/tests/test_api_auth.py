"""API token middleware protects /api/* and /metrics."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.auth import ApiTokenMiddleware
from app.api.metrics import metrics_router
from app.api.routes import router
from app.models import SystemStatus, utcnow


@pytest.fixture
def authed_client():
    orch = MagicMock()
    orch.build_status.return_value = SystemStatus(
        ha_connected=True,
        telemetry_stale=False,
        telemetry_age_seconds=1.0,
        forecast_misconfigured=False,
        forecast_degraded=False,
        engine_mode="rules",
        engine_active="rules",
        shadow_mode=True,
        paused=False,
        last_updated=utcnow(),
    )
    app = FastAPI()
    app.state.orchestrator = orch
    app.add_middleware(ApiTokenMiddleware, token="secret-token")
    app.include_router(metrics_router)
    app.include_router(router)
    return TestClient(app)


def test_health_public_without_token(authed_client):
    res = authed_client.get("/api/health")
    assert res.status_code == 200


def test_status_requires_token(authed_client):
    res = authed_client.get("/api/status")
    assert res.status_code == 401


def test_status_with_bearer_token(authed_client):
    res = authed_client.get(
        "/api/status",
        headers={"Authorization": "Bearer secret-token"},
    )
    assert res.status_code == 200


def test_metrics_requires_token(authed_client):
    res = authed_client.get("/metrics")
    assert res.status_code == 401
