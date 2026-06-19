"""ML model import sticky lock and retrain."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import router
from app.models import SystemStatus, utcnow


@pytest.fixture
def client():
    orch = MagicMock()
    forecast = MagicMock()
    forecast.ml_import_locked = False
    forecast._refresh_lock = __import__("asyncio").Lock()
    forecast.import_model = MagicMock()
    forecast.save_model = MagicMock()
    forecast.retrain_ml_load = AsyncMock(return_value=True)
    orch.forecast = forecast
    orch.forecast_cycle = AsyncMock()
    orch.model_path = "/tmp/model.json"
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
    app.include_router(router)
    return TestClient(app), orch


def test_model_retrain_endpoint(client):
    tc, orch = client
    res = tc.post("/api/model/retrain")
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["trained"] is True
    orch.forecast.retrain_ml_load.assert_awaited_once()
    orch.forecast.save_model.assert_called_once()
    orch.forecast_cycle.assert_awaited_once()


@pytest.mark.asyncio
async def test_import_lock_skips_train(monkeypatch):
    from app.config import AppConfig, Settings
    from app.forecast.service import ForecastService
    from app.models import LoadForecastPoint, Telemetry, utcnow

    settings = Settings(ml_load_enabled=False)
    svc = ForecastService(AppConfig(), settings)

    ml = MagicMock()
    ml.trained = True
    ml.forecast.return_value = [
        LoadForecastPoint(ts=utcnow(), load_power_w=400.0),
    ]
    svc._ml_load = ml
    svc._ml_import_locked = True

    async def fake_history(*_a, **_k):
        return [
            Telemetry(ts=utcnow(), battery_soc=50.0, load_power=400.0)
            for _ in range(250)
        ]

    monkeypatch.setattr("app.forecast.service.repo.get_telemetry_since", fake_history)
    monkeypatch.setattr(
        "app.forecast.service.ForecastService._update_bias_from_history",
        lambda self, h: None,
    )
    monkeypatch.setattr(
        "app.forecast.service.ForecastService._temperature_points",
        lambda self, tl: ([], 0.0, 0.0),
    )

    with patch.object(svc._solar, "forecast", new_callable=AsyncMock) as solar:
        solar.return_value = []
        with patch.object(svc._load, "train") as heuristic_train:
            await svc.refresh()
    ml.train.assert_not_called()
    ml.forecast.assert_called_once()
    heuristic_train.assert_not_called()
