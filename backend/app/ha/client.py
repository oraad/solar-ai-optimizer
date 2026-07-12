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
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

import httpx
import websockets

from ..models import utcnow

log = logging.getLogger("ha.client")

# Backoff / circuit defaults (seconds)
_TRANSIENT_MIN = 5.0
_TRANSIENT_MAX = 60.0
_BANNED_MIN = 60.0
_BANNED_MAX = 900.0  # 15 minutes
_AUTH_INVALID_OPEN_AFTER = 2
_BANNED_OPEN_AFTER = 3
_CIRCUIT_PROBE_INTERVAL = 300.0  # 5 minutes soft REST probe while open
_ERROR_TRUNCATE = 240


class HAError(Exception):
    """Raised on Home Assistant communication failures."""


class HAAuthInvalid(HAError):
    """WebSocket (or REST) authentication was rejected by Home Assistant."""


class WsErrorClass(StrEnum):
    """Classification of WebSocket reconnect failures."""

    NONE = "none"
    TRANSIENT = "transient"
    AUTH_INVALID = "auth_invalid"
    BANNED_OR_FORBIDDEN = "banned_or_forbidden"


def classify_ws_error(exc: BaseException) -> WsErrorClass:
    """Map an exception from the WS connect/auth path to an error class."""
    if isinstance(exc, HAAuthInvalid):
        return WsErrorClass.AUTH_INVALID
    text = str(exc).lower()
    # websockets raises InvalidStatus / InvalidStatusCode with HTTP status
    status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
    if status == 403 or " 403" in text or "status 403" in text or "forbidden" in text:
        return WsErrorClass.BANNED_OR_FORBIDDEN
    if "auth_invalid" in text or "websocket auth failed" in text:
        return WsErrorClass.AUTH_INVALID
    return WsErrorClass.TRANSIENT


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

        # Reconnect / circuit state (survives within process; reset on new client)
        self.last_ws_error: str | None = None
        self.last_ws_error_class: WsErrorClass = WsErrorClass.NONE
        self.ws_backoff_seconds: float = _TRANSIENT_MIN
        self.ws_circuit_open: bool = False
        self.ws_next_retry_at: datetime | None = None
        self._auth_fail_count: int = 0
        self._banned_fail_count: int = 0
        self._circuit_opened_at: datetime | None = None
        self._force_retry: asyncio.Event = asyncio.Event()

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
            return "wss" + self._base_url[len("https") :] + "/api/websocket"
        return "ws" + self._base_url[len("http") :] + "/api/websocket"

    def _ssl_context(self) -> ssl.SSLContext | None:
        if not self._ws_url().startswith("wss"):
            return None
        ctx = ssl.create_default_context()
        if not self._verify_ssl:
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        return ctx

    def request_retry(self) -> None:
        """Close the circuit and wake the reconnect loop (admin Retry)."""
        self.ws_circuit_open = False
        self._circuit_opened_at = None
        self._auth_fail_count = 0
        self._banned_fail_count = 0
        self.ws_backoff_seconds = _TRANSIENT_MIN
        self.ws_next_retry_at = None
        self._force_retry.set()

    def ws_diagnostics(self) -> dict[str, Any]:
        """Snapshot of WS reconnect / circuit state for health APIs."""
        next_at = self.ws_next_retry_at
        return {
            "ha_ws_error_class": (
                None
                if self.last_ws_error_class == WsErrorClass.NONE
                else str(self.last_ws_error_class)
            ),
            "ha_ws_last_error": self.last_ws_error,
            "ha_ws_circuit_open": self.ws_circuit_open,
            "ha_ws_backoff_seconds": self.ws_backoff_seconds,
            "ha_ws_next_retry_at": next_at.isoformat() if next_at else None,
        }

    def _record_success(self) -> None:
        self.last_ws_error = None
        self.last_ws_error_class = WsErrorClass.NONE
        self.ws_backoff_seconds = _TRANSIENT_MIN
        self.ws_circuit_open = False
        self.ws_next_retry_at = None
        self._auth_fail_count = 0
        self._banned_fail_count = 0
        self._circuit_opened_at = None

    def _record_failure(self, exc: BaseException) -> float:
        """Update circuit/backoff state; return seconds to sleep before next attempt."""
        cls = classify_ws_error(exc)
        prev_class = self.last_ws_error_class
        msg = str(exc)
        if len(msg) > _ERROR_TRUNCATE:
            msg = msg[: _ERROR_TRUNCATE - 3] + "..."
        self.last_ws_error = msg
        self.last_ws_error_class = cls
        self.connected = False

        if cls == WsErrorClass.AUTH_INVALID:
            self._auth_fail_count += 1
            self._banned_fail_count = 0
            if self._auth_fail_count >= _AUTH_INVALID_OPEN_AFTER:
                self.ws_circuit_open = True
                self._circuit_opened_at = utcnow()
                self.ws_backoff_seconds = _CIRCUIT_PROBE_INTERVAL
            else:
                self.ws_backoff_seconds = _TRANSIENT_MIN
        elif cls == WsErrorClass.BANNED_OR_FORBIDDEN:
            self._banned_fail_count += 1
            self._auth_fail_count = 0
            prev = self.ws_backoff_seconds
            if prev < _BANNED_MIN:
                self.ws_backoff_seconds = _BANNED_MIN
            else:
                self.ws_backoff_seconds = min(prev * 2.0, _BANNED_MAX)
            if self._banned_fail_count >= _BANNED_OPEN_AFTER:
                self.ws_circuit_open = True
                self._circuit_opened_at = utcnow()
                self.ws_backoff_seconds = max(
                    self.ws_backoff_seconds, _CIRCUIT_PROBE_INTERVAL
                )
        else:
            # First transient after success/other class uses MIN; then exponential.
            self._auth_fail_count = 0
            self._banned_fail_count = 0
            if prev_class != WsErrorClass.TRANSIENT:
                self.ws_backoff_seconds = _TRANSIENT_MIN
            else:
                self.ws_backoff_seconds = min(
                    self.ws_backoff_seconds * 2.0, _TRANSIENT_MAX
                )

        delay = self.ws_backoff_seconds
        self.ws_next_retry_at = utcnow() + timedelta(seconds=delay)
        return delay

    async def _wait_before_retry(self, delay: float) -> None:
        """Sleep ``delay`` seconds, or wake early on ``request_retry()``."""
        self._force_retry.clear()
        try:
            await asyncio.wait_for(self._force_retry.wait(), timeout=delay)
        except TimeoutError:
            pass

    async def _wait_while_circuit_open(self) -> None:
        """While circuit is open: soft REST probe on an interval; wake on Retry."""
        while self.ws_circuit_open:
            self.ws_next_retry_at = utcnow() + timedelta(seconds=_CIRCUIT_PROBE_INTERVAL)
            self._force_retry.clear()
            try:
                await asyncio.wait_for(
                    self._force_retry.wait(), timeout=_CIRCUIT_PROBE_INTERVAL
                )
                # Explicit retry — leave circuit closed by request_retry()
                return
            except TimeoutError:
                pass
            # Soft probe: one REST GET /api/ — if 200, close circuit and retry WS
            if await self.ping():
                log.info(
                    "HA REST probe succeeded while circuit open; retrying WebSocket"
                )
                self.ws_circuit_open = False
                self._circuit_opened_at = None
                self._auth_fail_count = 0
                self._banned_fail_count = 0
                self.ws_backoff_seconds = _TRANSIENT_MIN
                return
            log.warning(
                "HA WebSocket circuit open (%s); next probe in %ss — %s",
                self.last_ws_error_class,
                _CIRCUIT_PROBE_INTERVAL,
                self.last_ws_error,
            )

    async def stream_states(
        self, reconnect_delay: float = 5.0
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield `state_changed` event payloads, reconnecting on failure.

        Each yielded item is the HA event ``data`` dict containing
        ``entity_id``, ``old_state`` and ``new_state``.

        ``reconnect_delay`` is the initial transient backoff (kept for API
        compatibility); auth/ban failures use longer classified backoffs.
        """
        if reconnect_delay > 0:
            self.ws_backoff_seconds = float(reconnect_delay)
        url = self._ws_url()
        while True:
            if self.ws_circuit_open:
                await self._wait_while_circuit_open()
            try:
                async with websockets.connect(
                    url, ssl=self._ssl_context(), max_size=8 * 1024 * 1024
                ) as ws:
                    await self._ws_authenticate(ws)
                    await self._ws_subscribe(ws, "state_changed")
                    self.connected = True
                    self._record_success()
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
                delay = self._record_failure(e)
                log.warning(
                    "HA WebSocket error [%s] (%s); reconnecting in %ss%s",
                    self.last_ws_error_class,
                    e,
                    delay,
                    " (circuit open)" if self.ws_circuit_open else "",
                )
                if self.ws_circuit_open:
                    await self._wait_while_circuit_open()
                else:
                    await self._wait_before_retry(delay)

    async def _ws_authenticate(self, ws: Any) -> None:
        # First frame from server is auth_required.
        greeting = json.loads(await ws.recv())
        if greeting.get("type") != "auth_required":
            raise HAError(f"Unexpected greeting: {greeting}")
        await ws.send(json.dumps({"type": "auth", "access_token": self._token}))
        result = json.loads(await ws.recv())
        if result.get("type") != "auth_ok":
            raise HAAuthInvalid(f"WebSocket auth failed: {result}")

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
