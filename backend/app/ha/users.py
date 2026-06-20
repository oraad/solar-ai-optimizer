"""Home Assistant user admin lookup via WebSocket config/auth/list."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

import websockets

from ..config import Settings
from .client import HAClient, HAError

log = logging.getLogger("ha.users")

SYSTEM_ADMIN_GROUP = "system-admin"


class HAAdminResolver:
    """Cache whether a HA user id has admin privileges."""

    def __init__(self, settings: Settings, ha: HAClient) -> None:
        self._settings = settings
        self._ha = ha
        self._cache: dict[str, tuple[bool, float]] = {}
        self._users: dict[str, dict[str, Any]] | None = None
        self._users_loaded_at: float = 0.0
        self._lock = asyncio.Lock()

    def _ttl(self) -> float:
        return max(30, self._settings.admin_cache_ttl_seconds)

    def set_ha(self, ha: HAClient) -> None:
        """Point at a new HA client after reconnect; clears cached user list."""
        self._ha = ha
        self._cache.clear()
        self._users = None
        self._users_loaded_at = 0.0

    async def is_admin(self, user_id: str) -> bool:
        if user_id in self._settings.admin_user_id_set:
            return True
        now = time.time()
        cached = self._cache.get(user_id)
        if cached and now - cached[1] < self._ttl():
            return cached[0]
        users = await self._load_users()
        user = users.get(user_id)
        is_admin = _user_is_admin(user) if user else False
        self._cache[user_id] = (is_admin, now)
        return is_admin

    async def _load_users(self) -> dict[str, dict[str, Any]]:
        now = time.time()
        if self._users is not None and now - self._users_loaded_at < self._ttl():
            return self._users
        async with self._lock:
            if self._users is not None and now - self._users_loaded_at < self._ttl():
                return self._users
            users = await _fetch_auth_list(self._ha)
            self._users = users
            self._users_loaded_at = time.time()
            return users


def _user_is_admin(user: dict[str, Any]) -> bool:
    if user.get("is_owner"):
        return True
    group_ids = user.get("group_ids") or []
    return SYSTEM_ADMIN_GROUP in group_ids


async def _fetch_auth_list(ha: HAClient) -> dict[str, dict[str, Any]]:
    if not ha._token:
        return {}
    url = ha._ws_url()
    try:
        async with websockets.connect(
            url, ssl=ha._ssl_context(), max_size=2 * 1024 * 1024
        ) as ws:
            greeting = json.loads(await ws.recv())
            if greeting.get("type") != "auth_required":
                raise HAError(f"Unexpected greeting: {greeting}")
            await ws.send(
                json.dumps({"type": "auth", "access_token": ha._token})
            )
            auth_result = json.loads(await ws.recv())
            if auth_result.get("type") != "auth_ok":
                raise HAError(f"WebSocket auth failed: {auth_result}")

            msg_id = 1
            await ws.send(
                json.dumps({"id": msg_id, "type": "config/auth/list"})
            )
            while True:
                raw = json.loads(await ws.recv())
                if raw.get("id") != msg_id:
                    continue
                if not raw.get("success"):
                    log.warning("config/auth/list failed: %s", raw)
                    return {}
                result = raw.get("result") or []
                return {u["id"]: u for u in result if u.get("id")}
    except Exception as e:  # noqa: BLE001
        log.warning("Failed to fetch HA config/auth/list: %s", e)
        return {}
