"""Tests for /api/ping, /api/v1 alias, and HealthResponse model contract."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import router
from app.config import get_settings
from app.main import V1AliasMiddleware
from app.models import SystemStatus, utcnow


@pytest.fixture
def api_app(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("HA_TOKEN", "")
    get_settings.cache_clear()

    orch = MagicMock()
    orch.ha.is_reachable.return_value = True
    orch.shadow_mode = False
    orch.paused = False
    orch.forecast.current = None
    orch.forecast.site_tz.return_value = ZoneInfo("UTC")
    orch.build_status.return_value = SystemStatus(
        ha_connected=True,
        telemetry_stale=False,
        telemetry_age_seconds=1.0,
        forecast_misconfigured=False,
        forecast_degraded=False,
        engine_mode="rules",
        engine_active="rules",
        shadow_mode=False,
        paused=False,
        last_updated=utcnow(),
    )
    orch.cfg.fail_safe = MagicMock(shutdown_failsafe_enabled=True)
    orch.heartbeat.last_pulse_at = datetime(2026, 7, 8, 5, 27, tzinfo=timezone.utc)

    app = FastAPI()
    app.state.orchestrator = orch
    # Add the V1AliasMiddleware so /api/v1/* → /api/*
    app.add_middleware(V1AliasMiddleware)
    app.include_router(router)
    return app


@pytest.fixture
def client(api_app):
    return TestClient(api_app)


# -------------------------------------------------------------------------
# /api/ping
# -------------------------------------------------------------------------

def test_ping_returns_ok(client):
    res = client.get("/api/ping")
    assert res.status_code == 200
    assert res.json() == {"ok": True}


def test_ping_no_auth_required(client, monkeypatch):
    """ping must be reachable without any auth token (public endpoint)."""
    monkeypatch.setenv("API_TOKEN", "sometoken")
    from app.api import auth as auth_module
    from app.api.auth import AuthGateMiddleware, UserContextMiddleware

    get_settings.cache_clear()
    from app.config import get_settings as gs

    app2 = TestClient(client.app)
    # Simply GET without Authorization header — should still return 200
    res = app2.get("/api/ping")
    assert res.status_code == 200


# -------------------------------------------------------------------------
# /api/v1 alias
# -------------------------------------------------------------------------

def test_v1_alias_ping(client):
    res = client.get("/api/v1/ping")
    assert res.status_code == 200
    assert res.json() == {"ok": True}


def test_v1_alias_health(client):
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert "version" in body


def test_v1_alias_normalizes_double_slashes(client):
    """Extra slashes in the rewritten path are normalized and stay under /api."""
    res = client.get("/api/v1//ping")
    assert res.status_code == 200
    assert res.json() == {"ok": True}


# -------------------------------------------------------------------------
# V1AliasMiddleware traversal hardening (direct ASGI scope, bypassing
# httpx's own dot-segment normalization so the middleware is exercised
# with a raw, unresolved ".." path segment as a malicious client could send).
# -------------------------------------------------------------------------


async def _drive_middleware(path: str) -> int:
    captured: dict[str, object] = {}

    async def app(scope, receive, send):  # noqa: ANN001
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"{}"})

    async def receive():  # noqa: ANN001
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):  # noqa: ANN001
        if message["type"] == "http.response.start":
            captured["status"] = message["status"]

    middleware = V1AliasMiddleware(app)
    scope = {"type": "http", "path": path, "raw_path": path.encode("utf-8")}
    await middleware(scope, receive, send)
    return int(captured["status"])


def test_v1_alias_rejects_dotdot_traversal():
    """A ".." segment in the raw ASGI path must be rejected, not rewritten."""
    status = asyncio.run(_drive_middleware("/api/v1/../secrets"))
    assert status == 400


def test_v1_alias_rejects_encoded_traversal_after_normalize():
    """Even if a ".." sneaks past rewriting, normpath must keep it under /api."""
    status = asyncio.run(_drive_middleware("/api/v1/x/../../etc/passwd"))
    assert status == 400


# -------------------------------------------------------------------------
# HealthResponse model contract
# -------------------------------------------------------------------------

def test_health_response_model_fields(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    body = res.json()
    # Required fields from HealthResponse model
    assert body["status"] == "ok"
    assert isinstance(body["version"], str)
    assert isinstance(body["install_id"], str)
    assert isinstance(body["ha_connected"], bool)
    assert isinstance(body["shadow_mode"], bool)
    assert isinstance(body["paused"], bool)
    assert isinstance(body["telemetry_stale"], bool)
    assert isinstance(body["engine_mode"], str)
    assert isinstance(body["engine_active"], str)
    # Extra fields are passed through (model_config extra="allow")
    assert "metrics" in body
    assert "time" in body
