"""Security-related app factory behavior."""

from __future__ import annotations

import bcrypt
import pytest
from fastapi.testclient import TestClient

from tests.conftest_auth import clear_auth_env


@pytest.fixture
def authed_app(tmp_path, monkeypatch):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("battery:\n  capacity_kwh: 10\n", encoding="utf-8")
    data = tmp_path / "data"
    data.mkdir()
    password_hash = bcrypt.hashpw(b"secret", bcrypt.gensalt()).decode()
    monkeypatch.setenv("CONFIG_PATH", str(cfg))
    monkeypatch.setenv("DATA_DIR", str(data))
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{data / 'test.db'}")
    monkeypatch.setenv("LOCAL_ADMIN_PASSWORD_HASH", password_hash)
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    monkeypatch.setenv("HA_TOKEN", "")
    monkeypatch.setenv("HA_BASE_URL", "http://127.0.0.1:9")
    # TestClient talks plain http://testserver; a Secure cookie would be
    # dropped by the client, so opt out like a non-TLS deployment would.
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")

    from app.config import get_settings

    get_settings.cache_clear()

    from app.main import create_app

    with TestClient(create_app()) as client:
        yield client


def test_openapi_protected_when_local_auth_set(authed_app):
    """OpenAPI schema and docs are now gated (401) rather than hidden (404)."""
    assert authed_app.get("/openapi.json").status_code == 401
    assert authed_app.get("/docs").status_code == 401


def test_status_requires_login_when_local_auth(authed_app):
    assert authed_app.get("/api/status").status_code == 401
    authed_app.post("/api/auth/login", json={"username": "admin", "password": "secret"})
    assert authed_app.get("/api/status").status_code == 200


@pytest.fixture
def app_env(tmp_path, monkeypatch):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("battery:\n  capacity_kwh: 10\n", encoding="utf-8")
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setenv("CONFIG_PATH", str(cfg))
    monkeypatch.setenv("DATA_DIR", str(data))
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{data / 'test.db'}")
    monkeypatch.setenv("HA_TOKEN", "")
    monkeypatch.setenv("HA_BASE_URL", "http://127.0.0.1:9")
    clear_auth_env(monkeypatch)


def _open_client():
    from app.main import create_app

    return TestClient(create_app())


def test_x_frame_options_deny_without_ingress_trust(app_env):
    """Standalone mode: ingress_trusted is false → DENY."""
    with _open_client() as client:
        res = client.get("/api/health")
    assert res.status_code == 200
    assert res.headers.get("X-Frame-Options") == "DENY"


def test_x_frame_options_sameorigin_when_ingress_trusted(app_env, monkeypatch):
    """TRUST_INGRESS_HEADERS=true → ingress_trusted → SAMEORIGIN."""
    monkeypatch.setenv("TRUST_INGRESS_HEADERS", "true")
    monkeypatch.setenv("TRUSTED_PROXY_IPS", "127.0.0.1")
    from app.config import get_settings

    get_settings.cache_clear()

    with _open_client() as client:
        res = client.get("/api/health")
    assert res.status_code == 200
    assert res.headers.get("X-Frame-Options") == "SAMEORIGIN"


def test_x_frame_options_sameorigin_when_addon(app_env, monkeypatch):
    """SUPERVISOR_TOKEN → is_addon → ingress_trusted → SAMEORIGIN."""
    monkeypatch.setenv("SUPERVISOR_TOKEN", "supervisor-token")
    from app.config import get_settings

    get_settings.cache_clear()

    with _open_client() as client:
        res = client.get("/api/health")
    assert res.status_code == 200
    assert res.headers.get("X-Frame-Options") == "SAMEORIGIN"
