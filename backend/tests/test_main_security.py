"""Security-related app factory behavior."""

from __future__ import annotations

import bcrypt
import pytest
from fastapi.testclient import TestClient


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

    from app.config import get_settings

    get_settings.cache_clear()

    from app.main import create_app

    with TestClient(create_app()) as client:
        yield client


def test_openapi_hidden_when_local_auth_set(authed_app):
    assert authed_app.get("/openapi.json").status_code == 404
    assert authed_app.get("/docs").status_code == 404


def test_status_requires_login_when_local_auth(authed_app):
    assert authed_app.get("/api/status").status_code == 401
    authed_app.post("/api/auth/login", json={"username": "admin", "password": "secret"})
    assert authed_app.get("/api/status").status_code == 200
