"""Local admin login and logout."""

from __future__ import annotations

import bcrypt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.auth import AuthGateMiddleware, UserContextMiddleware
from app.api.auth_routes import router as auth_router
from app.api.routes import router as api_router


@pytest.fixture
def login_client(monkeypatch):
    password_hash = bcrypt.hashpw(b"secret", bcrypt.gensalt()).decode()
    monkeypatch.setenv("LOCAL_ADMIN_USERNAME", "admin")
    monkeypatch.setenv("LOCAL_ADMIN_PASSWORD_HASH", password_hash)
    monkeypatch.setenv("SESSION_SECRET", "test-session-secret")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("HA_TOKEN", "")
    monkeypatch.setenv("HA_BASE_URL", "http://127.0.0.1:9")
    # TestClient talks plain http://testserver; a Secure cookie would be
    # dropped by the client, so opt out like a non-TLS deployment would.
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")

    from app.config import get_settings

    get_settings.cache_clear()

    app = FastAPI()
    app.add_middleware(AuthGateMiddleware)
    app.add_middleware(UserContextMiddleware)
    app.include_router(auth_router)
    app.include_router(api_router)
    return TestClient(app)


def test_login_success_sets_cookie(login_client):
    res = login_client.post("/api/auth/login", json={"username": "admin", "password": "secret"})
    assert res.status_code == 200
    cookie = res.headers.get("set-cookie", "")
    assert "solar_session=" in cookie
    assert "Secure" not in cookie


def test_default_session_cookie_secure_is_false(monkeypatch):
    """HTTP Proxmox/LAN must not emit Secure cookies unless explicitly enabled."""
    monkeypatch.delenv("SESSION_COOKIE_SECURE", raising=False)
    from app.config import Settings, get_settings

    get_settings.cache_clear()
    assert Settings().session_cookie_secure is False


def test_login_bad_password(login_client):
    res = login_client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
    assert res.status_code == 401


def test_me_requires_login_then_succeeds(login_client):
    assert login_client.get("/api/me").status_code == 401
    login_client.post("/api/auth/login", json={"username": "admin", "password": "secret"})
    me = login_client.get("/api/me")
    assert me.status_code == 200
    body = me.json()
    assert body["auth_mode"] == "local"
    assert body["is_admin"] is True


def test_logout_clears_session(login_client):
    login_client.post("/api/auth/login", json={"username": "admin", "password": "secret"})
    login_client.post("/api/auth/logout")
    assert login_client.get("/api/me").status_code == 401
