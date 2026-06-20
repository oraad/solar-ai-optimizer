"""HA admin resolver: config/auth/list lookup and is_owner / group checks."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import Settings
from app.ha.client import HAClient
from app.ha.users import HAAdminResolver, _fetch_auth_list, _user_is_admin


def _settings(**kwargs) -> Settings:
    return Settings(
        ha_token="test-token",
        ha_base_url="http://127.0.0.1:8123",
        database_url="sqlite+aiosqlite:///:memory:",
        **kwargs,
    )


def _ha() -> HAClient:
    return HAClient("http://127.0.0.1:8123", "test-token", True)


@pytest.mark.parametrize(
    ("user", "expected"),
    [
        ({"is_owner": True, "group_ids": []}, True),
        ({"is_owner": False, "group_ids": ["system-admin"]}, True),
        ({"is_owner": False, "group_ids": ["users"]}, False),
        ({}, False),
    ],
)
def test_user_is_admin(user: dict, expected: bool):
    assert _user_is_admin(user) is expected


@pytest.mark.asyncio
async def test_resolver_allowlist_short_circuit():
    settings = _settings(admin_user_ids="owner-1")
    resolver = HAAdminResolver(settings, _ha())
    assert await resolver.is_admin("owner-1") is True


@pytest.mark.asyncio
async def test_resolver_owner_from_auth_list():
    settings = _settings()
    resolver = HAAdminResolver(settings, _ha())
    users = {
        "u1": {"id": "u1", "is_owner": True, "group_ids": []},
        "u2": {"id": "u2", "is_owner": False, "group_ids": ["users"]},
    }
    with patch.object(resolver, "_load_users", AsyncMock(return_value=users)):
        assert await resolver.is_admin("u1") is True
        assert await resolver.is_admin("u2") is False


@pytest.mark.asyncio
async def test_resolver_unknown_user_is_viewer():
    settings = _settings()
    resolver = HAAdminResolver(settings, _ha())
    with patch.object(resolver, "_load_users", AsyncMock(return_value={})):
        assert await resolver.is_admin("missing") is False


@pytest.mark.asyncio
async def test_resolver_set_ha_clears_cache():
    settings = _settings()
    resolver = HAAdminResolver(settings, _ha())
    resolver._cache["u1"] = (True, 0.0)
    resolver._users = {"u1": {"id": "u1", "is_owner": True}}
    new_ha = HAClient("http://192.168.1.2:8123", "other-token", True)
    resolver.set_ha(new_ha)
    assert resolver._ha is new_ha
    assert resolver._cache == {}
    assert resolver._users is None


@pytest.mark.asyncio
async def test_fetch_auth_list_sends_config_auth_list():
    ha = _ha()
    sent: list[str] = []

    class FakeWs:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):  # noqa: ANN002
            return None

        async def recv(self):
            if not self._queue:
                raise RuntimeError("unexpected recv")
            return self._queue.pop(0)

        async def send(self, data: str):
            sent.append(data)

        _queue = [
            json.dumps({"type": "auth_required"}),
            json.dumps({"type": "auth_ok"}),
            json.dumps(
                {
                    "id": 1,
                    "type": "result",
                    "success": True,
                    "result": [
                        {"id": "u1", "is_owner": True, "group_ids": []},
                    ],
                }
            ),
        ]

    with patch("app.ha.users.websockets.connect", return_value=FakeWs()):
        users = await _fetch_auth_list(ha)

    assert "config/auth/list" in sent[1]
    assert users == {"u1": {"id": "u1", "is_owner": True, "group_ids": []}}


@pytest.mark.asyncio
async def test_fetch_auth_list_failure_returns_empty():
    ha = MagicMock()
    ha._token = "tok"
    ha._ws_url.return_value = "ws://127.0.0.1:8123/api/websocket"
    ha._ssl_context.return_value = None

    with patch(
        "app.ha.users.websockets.connect",
        side_effect=OSError("connection refused"),
    ):
        assert await _fetch_auth_list(ha) == {}


@pytest.mark.asyncio
async def test_fetch_auth_list_no_token():
    ha = MagicMock()
    ha._token = ""
    assert await _fetch_auth_list(ha) == {}
