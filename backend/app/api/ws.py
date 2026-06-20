"""WebSocket endpoint pushing live status snapshots to the dashboard."""

from __future__ import annotations

import asyncio
import contextlib
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from websockets.exceptions import ConnectionClosed, ConnectionClosedError, ConnectionClosedOK

from ..config import get_settings
from ..orchestrator import Orchestrator
from .session import get_session, resolve_session

log = logging.getLogger("api.ws")

ws_router = APIRouter()


async def _ws_authorized(websocket: WebSocket) -> bool:
    settings = get_settings()
    if hasattr(websocket.state, "session"):
        session = get_session(websocket)
    else:
        resolver = getattr(websocket.app.state, "admin_resolver", None)
        session = await resolve_session(websocket, settings, resolver)
        websocket.state.session = session

    if session.authenticated:
        return True

    if settings.local_auth_enabled or settings.api_token:
        return False
    return True


@ws_router.websocket("/ws")
async def ws_status(websocket: WebSocket) -> None:
    if not await _ws_authorized(websocket):
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
    except (ConnectionClosed, ConnectionClosedOK, ConnectionClosedError):
        log.debug("WebSocket client disconnected (keepalive or close)")
    except Exception as e:  # noqa: BLE001
        log.debug("WebSocket closed: %s", e)
    finally:
        orch.unsubscribe(queue)
