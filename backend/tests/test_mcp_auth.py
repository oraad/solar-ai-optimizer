"""MCP HTTP auth middleware."""

from __future__ import annotations

import pytest
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from app.mcp.auth import wrap_mcp_app


async def ok(request):  # noqa: ANN001
    return PlainTextResponse("ok")


@pytest.fixture
def auth_app(monkeypatch):
    monkeypatch.setenv("MCP_TOKEN", "mcp-secret")
    monkeypatch.setenv("API_TOKEN", "")
    from app.config import get_settings

    get_settings.cache_clear()
    settings = get_settings()
    inner = Starlette(routes=[Route("/", ok)])
    return wrap_mcp_app(inner, settings)


def test_mcp_auth_rejects_missing_bearer(auth_app):
    client = TestClient(auth_app)
    res = client.get("/")
    assert res.status_code == 401


def test_mcp_auth_accepts_valid_bearer(auth_app):
    client = TestClient(auth_app)
    res = client.get("/", headers={"Authorization": "Bearer mcp-secret"})
    assert res.status_code == 200


def test_mcp_auth_rejects_wrong_bearer(auth_app):
    client = TestClient(auth_app)
    res = client.get("/", headers={"Authorization": "Bearer wrong"})
    assert res.status_code == 403
