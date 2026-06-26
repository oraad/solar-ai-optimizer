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
