"""Precompressed static file serving."""

from __future__ import annotations

import gzip
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.conftest_auth import clear_auth_env

JS_BODY = b"console.log('solar');\n" * 80  # > 1 KB uncompressed


@pytest.fixture
def static_app(tmp_path, monkeypatch):
    static_dir = tmp_path / "static"
    assets = static_dir / "assets"
    assets.mkdir(parents=True)

    (assets / "app.js").write_bytes(JS_BODY)
    (assets / "app.js.gz").write_bytes(gzip.compress(JS_BODY))
    (assets / "app.js.br").write_bytes(b"br-sidecar-" + JS_BODY[:64])

    (static_dir / "index.html").write_text("<!doctype html><html></html>", encoding="utf-8")
    (static_dir / "index.html.br").write_bytes(b"br-index")

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
    clear_auth_env(monkeypatch)

    import app.main as main_module

    monkeypatch.setattr(main_module, "STATIC_DIR", str(static_dir))

    from app.config import get_settings

    get_settings.cache_clear()

    from app.main import create_app

    with TestClient(create_app()) as client:
        yield client, static_dir


def test_serves_brotli_sidecar(static_app):
    client, _static_dir = static_app
    res = client.get("/assets/app.js", headers={"Accept-Encoding": "br"})
    assert res.status_code == 200
    assert res.headers["content-encoding"] == "br"
    assert res.headers["vary"] == "Accept-Encoding"
    assert "javascript" in res.headers["content-type"]
    assert res.content == b"br-sidecar-" + JS_BODY[:64]


def test_serves_gzip_sidecar(static_app):
    client, _static_dir = static_app
    res = client.get("/assets/app.js", headers={"Accept-Encoding": "gzip"})
    assert res.status_code == 200
    assert res.headers["content-encoding"] == "gzip"
    assert res.headers["vary"] == "Accept-Encoding"
    # httpx TestClient auto-decompresses gzip responses.
    assert res.content == JS_BODY


def test_prefers_brotli_over_gzip(static_app):
    client, _static_dir = static_app
    res = client.get("/assets/app.js", headers={"Accept-Encoding": "br, gzip"})
    assert res.status_code == 200
    assert res.headers["content-encoding"] == "br"


def test_uncompressed_without_accept_encoding(static_app):
    client, _static_dir = static_app
    # httpx adds Accept-Encoding by default; identity-only skips sidecar negotiation.
    res = client.get("/assets/app.js", headers={"Accept-Encoding": "identity"})
    assert res.status_code == 200
    assert "content-encoding" not in res.headers
    assert res.content == JS_BODY


def test_gzip_middleware_fallback_without_sidecars(tmp_path, monkeypatch):
    static_dir = tmp_path / "static"
    assets = static_dir / "assets"
    assets.mkdir(parents=True)
    (assets / "app.js").write_bytes(JS_BODY)

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
    clear_auth_env(monkeypatch)

    import app.main as main_module

    monkeypatch.setattr(main_module, "STATIC_DIR", str(static_dir))

    from app.config import get_settings

    get_settings.cache_clear()

    from app.main import create_app

    with TestClient(create_app()) as client:
        res = client.get("/assets/app.js", headers={"Accept-Encoding": "gzip"})

    assert res.status_code == 200
    assert res.headers["content-encoding"] == "gzip"
    # httpx TestClient auto-decompresses gzip responses.
    assert res.content == JS_BODY


def test_spa_index_serves_brotli_sidecar(static_app):
    client, _static_dir = static_app
    res = client.get("/", headers={"Accept-Encoding": "br"})
    assert res.status_code == 200
    assert res.headers["content-encoding"] == "br"
    assert res.content == b"br-index"


def test_unit_accepts_encoding():
    from starlette.datastructures import Headers

    from app.compressed_static import _accepts_encoding

    headers = Headers({"accept-encoding": "gzip, deflate, br"})
    assert _accepts_encoding(headers, "br") is True
    assert _accepts_encoding(headers, "gzip") is True
    assert _accepts_encoding(Headers({}), "br") is False


def test_unit_pick_encoding_prefers_brotli(tmp_path):
    from starlette.datastructures import Headers

    from app.compressed_static import _pick_encoding

    asset = tmp_path / "app.js"
    asset.write_bytes(b"x")
    Path(f"{asset}.br").write_bytes(b"br")
    Path(f"{asset}.gz").write_bytes(b"gz")

    headers = Headers({"accept-encoding": "br, gzip"})
    assert _pick_encoding(headers, asset) == "br"

    Path(f"{asset}.br").unlink()
    assert _pick_encoding(headers, asset) == "gzip"
