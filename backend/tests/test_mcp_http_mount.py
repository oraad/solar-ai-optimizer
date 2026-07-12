"""MCP HTTP mount must win over the static UI catch-all."""

from __future__ import annotations

import gzip

import pytest
from fastapi.testclient import TestClient

from tests.conftest_auth import clear_auth_env

JS_BODY = b"console.log('solar');\n" * 80


@pytest.fixture
def mcp_static_client(tmp_path, monkeypatch):
    static_dir = tmp_path / "static"
    assets = static_dir / "assets"
    assets.mkdir(parents=True)
    (assets / "app.js").write_bytes(JS_BODY)
    (assets / "app.js.gz").write_bytes(gzip.compress(JS_BODY))
    (static_dir / "index.html").write_text("<!doctype html><html></html>", encoding="utf-8")

    cfg = tmp_path / "config.yaml"
    cfg.write_text("battery:\n  capacity_kwh: 10\n", encoding="utf-8")
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setenv("CONFIG_PATH", str(cfg))
    monkeypatch.setenv("DATA_DIR", str(data))
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{data / 'test.db'}")
    monkeypatch.setenv("STATIC_DIR", str(static_dir))
    monkeypatch.setenv("HA_TOKEN", "")
    monkeypatch.setenv("HA_BASE_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("MCP_ENABLED", "true")
    monkeypatch.setenv("MCP_TOKEN", "mcp-secret")
    clear_auth_env(monkeypatch)

    import app.main as main_module

    monkeypatch.setattr(main_module, "STATIC_DIR", str(static_dir))

    from app.config import get_settings

    get_settings.cache_clear()

    from app.main import create_app

    with TestClient(create_app()) as client:
        yield client


def test_mcp_post_not_swallowed_by_static(mcp_static_client: TestClient):
    """Static Files at / used to return 405 for POST /mcp; bearer middleware must run."""
    res = mcp_static_client.post(
        "/mcp",
        headers={
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        },
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "0"},
            },
        },
    )
    assert res.status_code == 401
    assert res.json().get("error") == "Bearer token required"


def test_mcp_post_accepts_bearer(mcp_static_client: TestClient):
    res = mcp_static_client.post(
        "/mcp",
        headers={
            "Authorization": "Bearer mcp-secret",
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        },
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "0"},
            },
        },
    )
    assert res.status_code != 405
    assert res.status_code != 401
    assert res.status_code != 403
    # initialize should succeed (200) once session manager + path are correct
    assert res.status_code == 200
