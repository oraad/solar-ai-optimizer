"""Tests for install_id and pairing clients."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.requests import Request
from zoneinfo import ZoneInfo

from app.api.auth import AuthGateMiddleware, UserContextMiddleware
from app.api.pair_routes import router as pair_router
from app.api.routes import router as api_router
from app.api.session import (
    credentials_configured,
    make_session_cookie,
    open_session,
    requires_auth_gate,
    resolve_session,
)
from app.auth import api_clients
from app.auth.install_id import get_or_create_install_id
from app.config import Settings, get_settings
from app.models import SystemStatus, utcnow
from tests.conftest import wire_orchestrator_site_tz


def test_install_id_stable(tmp_path: Path):
    a = get_or_create_install_id(tmp_path)
    b = get_or_create_install_id(tmp_path)
    assert a == b
    assert len(a) == 36


def test_pairing_roundtrip(tmp_path: Path):
    started = api_clients.start_pairing(tmp_path, created_by="admin")
    assert "-" in started["code"]
    minted = api_clients.redeem_pairing(
        tmp_path, code=started["code"], client_name="Home Assistant", client_ip="1.2.3.4"
    )
    assert minted["access_token"].startswith("sol_c_")
    client = api_clients.match_client_token(tmp_path, minted["access_token"])
    assert client is not None
    assert client.name == "Home Assistant"


def test_paired_clients_close_open_mode(tmp_path: Path):
    settings = Settings(
        ha_token="",
        database_url="sqlite+aiosqlite:///:memory:",
        data_dir=str(tmp_path),
    )
    assert open_session(settings) is not None
    assert not credentials_configured(settings)
    started = api_clients.start_pairing(tmp_path)
    api_clients.redeem_pairing(tmp_path, code=started["code"], client_name="HA")
    assert credentials_configured(settings)
    assert open_session(settings) is None
    assert requires_auth_gate("/api/status", settings) is True


def test_second_redeem_same_code_is_conflict(tmp_path: Path):
    started = api_clients.start_pairing(tmp_path)
    code = started["code"]
    api_clients.redeem_pairing(tmp_path, code=code, client_name="HA")
    with pytest.raises(api_clients.PairingError) as exc:
        api_clients.redeem_pairing(tmp_path, code=code, client_name="HA again")
    assert exc.value.code == "conflict"
    assert exc.value.status == 409


@pytest.mark.asyncio
async def test_bearer_paired_client(tmp_path: Path):
    started = api_clients.start_pairing(tmp_path)
    minted = api_clients.redeem_pairing(tmp_path, code=started["code"], client_name="HA")
    settings = Settings(
        ha_token="",
        database_url="sqlite+aiosqlite:///:memory:",
        data_dir=str(tmp_path),
    )
    hdrs = [(b"authorization", f"Bearer {minted['access_token']}".encode())]
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/status",
        "headers": hdrs,
        "query_string": b"",
        "client": ("127.0.0.1", 1),
        "server": ("test", 80),
        "scheme": "http",
        "root_path": "",
    }
    session = await resolve_session(Request(scope), settings, None)
    assert session.auth_mode == "client"
    assert session.is_admin is True


def test_pair_redeem_http(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("HA_TOKEN", "")
    monkeypatch.setenv("LOCAL_ADMIN_PASSWORD", "adminpass")
    monkeypatch.setenv("SESSION_SECRET", "secret")
    get_settings.cache_clear()

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
    fs = MagicMock()
    fs.heartbeat_enabled = True
    fs.heartbeat_entity = "input_datetime.x"
    orch.cfg.fail_safe = fs
    orch.heartbeat.last_pulse_at = None

    app = FastAPI()
    app.state.orchestrator = orch
    app.state.admin_resolver = AsyncMock()
    app.add_middleware(AuthGateMiddleware)
    app.add_middleware(UserContextMiddleware)
    app.include_router(api_router)
    app.include_router(pair_router)

    client = TestClient(app)
    health = client.get("/api/health")
    assert health.status_code == 200
    assert "install_id" in health.json()

    settings = get_settings()
    cookie = make_session_cookie("admin", settings)
    start = client.post(
        "/api/pair/start",
        cookies={"solar_session": cookie},
    )
    assert start.status_code == 200, start.text
    code = start.json()["code"]
    redeem = client.post(
        "/api/pair/redeem",
        json={"code": code, "client_name": "Home Assistant"},
    )
    assert redeem.status_code == 201, redeem.text
    body = redeem.json()
    assert body["access_token"].startswith("sol_c_")
    assert body["install_id"] == health.json()["install_id"]
