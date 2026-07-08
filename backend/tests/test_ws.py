"""WebSocket /ws endpoint tests."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.conftest_auth import clear_auth_env


@pytest.fixture
def live_client(tmp_path, monkeypatch):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "battery:\n  capacity_kwh: 10\nsite:\n  latitude: -33.9\n  longitude: 18.4\n",
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


@pytest.fixture
def authed_ws_client(tmp_path, monkeypatch):
    from unittest.mock import AsyncMock, MagicMock

    from app.models import SystemStatus, utcnow
    from tests.conftest import wire_orchestrator_site_tz

    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "battery:\n  capacity_kwh: 10\nsite:\n  latitude: -33.9\n  longitude: 18.4\n",
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
    monkeypatch.setenv("API_TOKEN", "ws-secret")

    from app.config import get_settings
    from app.main import create_app

    get_settings.cache_clear()
    app = create_app()
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
    wire_orchestrator_site_tz(orch)
    orch.subscribe = MagicMock(return_value=__import__("asyncio").Queue())
    orch.unsubscribe = MagicMock()
    app.state.orchestrator = orch
    app.state.admin_resolver = AsyncMock()

    with TestClient(app) as client:
        yield client


def test_ws_connect_receives_status_snapshot(live_client: TestClient):
    with live_client.websocket_connect("/ws") as ws:
        data = ws.receive_json()
        assert data.get("type") != "ping"
        assert "shadow_mode" in data
        assert "last_updated" in data


def test_ws_disconnect_closes_cleanly(live_client: TestClient):
    with live_client.websocket_connect("/ws") as ws:
        ws.receive_json()
    # Context exit closes the socket; handler must not raise.


def test_ws_rejects_when_gate_active_and_unauthenticated(authed_ws_client: TestClient):
    with pytest.raises(Exception):
        with authed_ws_client.websocket_connect("/ws"):
            pass


def test_ws_accepts_valid_query_token(authed_ws_client: TestClient):
    with authed_ws_client.websocket_connect("/ws?token=ws-secret") as ws:
        data = ws.receive_json()
        assert data.get("type") != "ping"
        assert "shadow_mode" in data
