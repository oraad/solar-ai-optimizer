"""WS ticket minting/consumption, jti binding, and MCP rejection."""

from __future__ import annotations

import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.auth import AuthGateMiddleware, UserContextMiddleware
from app.api.auth_routes import router as auth_router
from app.api.session import revoke_jti
from app.api.ws_tickets import (
    consume_ws_ticket,
    drop_tickets_for_jti,
    mint_ws_ticket,
)
from app.config import Settings
from tests.conftest_auth import clear_auth_env


def _settings(**kwargs) -> Settings:
    return Settings(
        ha_token="",
        database_url="sqlite+aiosqlite:///:memory:",
        **kwargs,
    )


def _admin_session():
    from app.api.session import SessionUser

    return SessionUser(
        user_id="local:admin",
        username="admin",
        display_name="admin",
        is_admin=True,
        auth_mode="local",
    )


def test_mint_and_consume_ticket_roundtrip():
    user = _admin_session()
    minted = mint_ws_ticket(user)
    assert "ticket" in minted
    consumed = consume_ws_ticket(minted["ticket"])
    assert consumed is user


def test_ticket_is_single_use():
    user = _admin_session()
    minted = mint_ws_ticket(user)
    assert consume_ws_ticket(minted["ticket"]) is not None
    assert consume_ws_ticket(minted["ticket"]) is None


def test_drop_tickets_for_jti_invalidates_outstanding_tickets():
    user = _admin_session()
    minted = mint_ws_ticket(user, jti="jti-to-drop")
    drop_tickets_for_jti("jti-to-drop")
    assert consume_ws_ticket(minted["ticket"]) is None


def test_consume_rejects_ticket_tied_to_revoked_jti():
    user = _admin_session()
    minted = mint_ws_ticket(user, jti="jti-revoked-directly")
    revoke_jti("jti-revoked-directly", time.time() + 3600)
    assert consume_ws_ticket(minted["ticket"]) is None


@pytest.fixture
def auth_client(monkeypatch, tmp_path):
    import bcrypt

    password_hash = bcrypt.hashpw(b"secret", bcrypt.gensalt()).decode()
    clear_auth_env(monkeypatch)
    monkeypatch.setenv("LOCAL_ADMIN_USERNAME", "admin")
    monkeypatch.setenv("LOCAL_ADMIN_PASSWORD_HASH", password_hash)
    monkeypatch.setenv("SESSION_SECRET", "test-session-secret")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("HA_TOKEN", "")
    monkeypatch.setenv("HA_BASE_URL", "http://127.0.0.1:9")
    # TestClient talks plain http://testserver; a Secure cookie would be
    # dropped by the client.
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")

    from app.config import get_settings

    get_settings.cache_clear()

    app = FastAPI()
    app.add_middleware(AuthGateMiddleware)
    app.add_middleware(UserContextMiddleware)
    app.include_router(auth_router)
    return TestClient(app)


def test_ws_ticket_requires_auth(auth_client):
    res = auth_client.post("/api/auth/ws-ticket")
    assert res.status_code == 401


def test_ws_ticket_mcp_bearer_rejected(auth_client, monkeypatch):
    monkeypatch.setenv("MCP_TOKEN", "mcp-secret")
    from app.config import get_settings

    get_settings.cache_clear()
    res = auth_client.post(
        "/api/auth/ws-ticket",
        headers={"Authorization": "Bearer mcp-secret"},
    )
    assert res.status_code == 403


def test_ws_ticket_local_session_then_logout_revokes_ticket(auth_client):
    auth_client.post("/api/auth/login", json={"username": "admin", "password": "secret"})
    res = auth_client.post("/api/auth/ws-ticket")
    assert res.status_code == 200
    ticket = res.json()["ticket"]

    auth_client.post("/api/auth/logout")

    assert consume_ws_ticket(ticket) is None
