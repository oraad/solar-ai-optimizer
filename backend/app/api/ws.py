"""WebSocket endpoint pushing live status snapshots to the dashboard."""

from __future__ import annotations

import asyncio
import contextlib
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..config import get_settings
from ..orchestrator import Orchestrator

log = logging.getLogger("api.ws")

ws_router = APIRouter()


def _ws_authorized(websocket: WebSocket) -> bool:
    settings = get_settings()
    if not settings.api_token:
        return True
    token = websocket.query_params.get("token", "")
    auth = websocket.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        token = token or auth[7:].strip()
    return token == settings.api_token


@ws_router.websocket("/ws")
async def ws_status(websocket: WebSocket) -> None:
    if not _ws_authorized(websocket):
        await websocket.close(code=4401, reason="Unauthorized")
        return
    orch: Orchestrator = websocket.app.state.orchestrator
    await websocket.accept()
    queue = orch.subscribe()
    # Send an immediate snapshot on connect.
    with contextlib.suppress(Exception):
        await websocket.send_json(orch.build_status().model_dump(mode="json"))
    try:
        while True:
            try:
                status = await asyncio.wait_for(queue.get(), timeout=30.0)
                await websocket.send_json(status)
            except asyncio.TimeoutError:
                # Heartbeat keepalive.
                await websocket.send_json({"type": "ping"})
    except WebSocketDisconnect:
        pass
    except Exception as e:  # noqa: BLE001
        log.debug("WebSocket closed: %s", e)
    finally:
        orch.unsubscribe(queue)
