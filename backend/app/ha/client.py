"""Home Assistant client: REST service calls + live WebSocket state stream.

Uses a long-lived access token. Exposes:
- `get_states()` / `get_state()`        - REST snapshot of entity states
- `call_service()`                       - REST service invocation (writes)
- `set_number()` / `select_option()` / `switch()` - typed helpers
- `stream_states()`                      - async generator of state_changed events
- `connected` / `last_seen`              - health for the watchdog
"""

from __future__ import annotations

import asyncio
import json
import logging
import ssl
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

import httpx
import websockets

from ..models import utcnow

log = logging.getLogger("ha.client")


class HAError(Exception):
    """Raised on Home Assistant communication failures."""


class HAClient:
    def __init__(self, base_url: str, token: str, verify_ssl: bool = True) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._verify_ssl = verify_ssl
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers=self._headers,
            verify=verify_ssl,
            timeout=httpx.Timeout(15.0),
        )
        self.connected: bool = False
        self.last_seen: datetime | None = None
        self._ws_id = 0

    # ----------------------------------------------------------------- REST --
    async def aclose(self) -> None:
        await self._client.aclose()

    async def get_states(self) -> list[dict[str, Any]]:
        try:
            resp = await self._client.get("/api/states")
            resp.raise_for_status()
            self._mark_seen()
            return resp.json()
        except httpx.HTTPError as e:
            raise HAError(f"get_states failed: {e}") from e

    async def get_state(self, entity_id: str) -> dict[str, Any] | None:
        try:
            resp = await self._client.get(f"/api/states/{entity_id}")
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            self._mark_seen()
            return resp.json()
        except httpx.HTTPError as e:
            raise HAError(f"get_state({entity_id}) failed: {e}") from e

    async def call_service(
        self, domain: str, service: str, data: dict[str, Any]
    ) -> Any:
        try:
            resp = await self._client.post(
                f"/api/services/{domain}/{service}", json=data
            )
            resp.raise_for_status()
            self._mark_seen()
            return resp.json()
        except httpx.HTTPError as e:
            raise HAError(f"call_service({domain}.{service}) failed: {e}") from e

    async def set_number(self, entity_id: str, value: float) -> None:
        await self.call_service(
            "number", "set_value", {"entity_id": entity_id, "value": value}
        )

    async def select_option(self, entity_id: str, option: str) -> None:
        await self.call_service(
            "select", "select_option", {"entity_id": entity_id, "option": option}
        )

    async def switch(self, entity_id: str, on: bool) -> None:
        await self.toggle_entity(entity_id, on)

    async def toggle_entity(self, entity_id: str, on: bool) -> None:
        """Turn an entity on/off using the correct HA domain service."""
        domain = entity_id.split(".", 1)[0] if entity_id else "switch"
        service = "turn_on" if on else "turn_off"
        await self.call_service(domain, service, {"entity_id": entity_id})

    async def ping(self) -> bool:
        """Lightweight reachability check against the REST API."""
        try:
            resp = await self._client.get("/api/")
            resp.raise_for_status()
            self._mark_seen()
            return True
        except httpx.HTTPError:
            return False

    # ------------------------------------------------------------ WebSocket --
    def _ws_url(self) -> str:
        if self._base_url.startswith("https"):
            return "wss" + self._base_url[len("https"):] + "/api/websocket"
        return "ws" + self._base_url[len("http"):] + "/api/websocket"

    def _ssl_context(self) -> ssl.SSLContext | None:
        if not self._ws_url().startswith("wss"):
            return None
        ctx = ssl.create_default_context()
        if not self._verify_ssl:
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        return ctx

    async def stream_states(
        self, reconnect_delay: float = 5.0
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield `state_changed` event payloads, reconnecting on failure.

        Each yielded item is the HA event ``data`` dict containing
        ``entity_id``, ``old_state`` and ``new_state``.
        """
        url = self._ws_url()
        while True:
            try:
                async with websockets.connect(
                    url, ssl=self._ssl_context(), max_size=8 * 1024 * 1024
                ) as ws:
                    await self._ws_authenticate(ws)
                    await self._ws_subscribe(ws, "state_changed")
                    self.connected = True
                    self._mark_seen()
                    log.info("HA WebSocket connected and subscribed.")
                    async for raw in ws:
                        msg = json.loads(raw)
                        if msg.get("type") == "event":
                            self._mark_seen()
                            data = msg.get("event", {}).get("data")
                            if data:
                                yield data
            except (OSError, websockets.WebSocketException, HAError) as e:
                self.connected = False
                log.warning(
                    "HA WebSocket error (%s); reconnecting in %ss", e, reconnect_delay
                )
                await asyncio.sleep(reconnect_delay)

    async def _ws_authenticate(self, ws: Any) -> None:
        # First frame from server is auth_required.
        greeting = json.loads(await ws.recv())
        if greeting.get("type") != "auth_required":
            raise HAError(f"Unexpected greeting: {greeting}")
        await ws.send(json.dumps({"type": "auth", "access_token": self._token}))
        result = json.loads(await ws.recv())
        if result.get("type") != "auth_ok":
            raise HAError(f"WebSocket auth failed: {result}")

    async def _ws_subscribe(self, ws: Any, event_type: str) -> None:
        self._ws_id += 1
        await ws.send(
            json.dumps(
                {
                    "id": self._ws_id,
                    "type": "subscribe_events",
                    "event_type": event_type,
                }
            )
        )
        result = json.loads(await ws.recv())
        if not result.get("success", False):
            raise HAError(f"subscribe_events failed: {result}")

    async def call_ws(self, msg_type: str, **kwargs: Any) -> Any:
        """One-shot WebSocket request/response (e.g. entity registry)."""
        url = self._ws_url()
        async with websockets.connect(
            url, ssl=self._ssl_context(), max_size=8 * 1024 * 1024
        ) as ws:
            await self._ws_authenticate(ws)
            self._ws_id += 1
            msg_id = self._ws_id
            payload: dict[str, Any] = {"id": msg_id, "type": msg_type, **kwargs}
            await ws.send(json.dumps(payload))
            while True:
                raw = await ws.recv()
                msg = json.loads(raw)
                if msg.get("id") != msg_id:
                    continue
                if not msg.get("success", True):
                    raise HAError(f"WS {msg_type} failed: {msg}")
                self._mark_seen()
                return msg.get("result")

    # --------------------------------------------------------------- health --
    def _mark_seen(self) -> None:
        self.last_seen = utcnow()

    def is_stale(self, stale_after_seconds: int) -> bool:
        if self.last_seen is None:
            return True
        return (utcnow() - self.last_seen).total_seconds() > stale_after_seconds

    def is_reachable(self, stale_after_seconds: int = 120) -> bool:
        """True when HA traffic (WS or REST) was seen recently."""
        return not self.is_stale(stale_after_seconds)
