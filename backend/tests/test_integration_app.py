"""Integration smoke test: real app lifespan + SQLite."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


from tests.conftest_auth import clear_auth_env


@pytest.fixture
def live_client(tmp_path, monkeypatch):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "battery:\n  capacity_kwh: 10\nforecast:\n  latitude: -33.9\n  longitude: 18.4\n",
        encoding="utf-8",
    )
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setenv("CONFIG_PATH", str(cfg))
    monkeypatch.setenv("DATA_DIR", str(data))
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{data / 'test.db'}")
    monkeypatch.setenv("HA_TOKEN", "")
    monkeypatch.setenv("HA_BASE_URL", "http://127.0.0.1:9")
    clear_auth_env(monkeypatch)

    from app.main import create_app

    with TestClient(create_app()) as client:
        yield client


def test_status_and_metrics_after_startup(live_client):
    health = live_client.get("/api/health")
    assert health.status_code == 200
    assert "engine_active" in health.json()

    metrics = live_client.get("/metrics")
    assert metrics.status_code == 200
    assert "solar_control_cycles_total" in metrics.text

    status = live_client.get("/api/status")
    assert status.status_code == 200
    body = status.json()
    assert "mpc_available" in body
    assert "ml_available" in body
    assert body["battery_summary"] is not None
    assert body["battery_summary"]["capacity_kwh"] == 10.0
