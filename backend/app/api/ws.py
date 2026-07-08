"""WebSocket endpoint pushing live status snapshots to the dashboard."""

from __future__ import annotations

import asyncio
import contextlib
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from websockets.exceptions import ConnectionClosed, ConnectionClosedError, ConnectionClosedOK

from ..config import get_settings
from ..i18n import reset_locale, resolve_request_locale, set_locale, t
from ..i18n.serialize import localize_model, localize_payload
from ..orchestrator import Orchestrator
from .session import get_session, resolve_session
from .timezone import site_tz_for

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

    return session.authenticated


@ws_router.websocket("/ws")
async def ws_status(websocket: WebSocket) -> None:
    loc = resolve_request_locale(
        websocket.query_params.get("locale"),
        websocket.headers.get("accept-language"),
    )
    token = set_locale(loc)
    try:
        if not await _ws_authorized(websocket):
            await websocket.close(code=4401, reason=t("api.auth.unauthorized"))
            return
        orch: Orchestrator = websocket.app.state.orchestrator
        await websocket.accept()
        queue = orch.subscribe()
        with contextlib.suppress(Exception):
            await websocket.send_json(
                localize_model(
                    orch.build_status(),
                    locale=loc,
                    site_tz=site_tz_for(orch),
                )
            )
        try:
            while True:
                try:
                    status = await asyncio.wait_for(queue.get(), timeout=30.0)
                    await websocket.send_json(
                        localize_payload(
                            status,
                            locale=loc,
                            site_tz=site_tz_for(orch),
                        )
                    )
                except asyncio.TimeoutError:
                    await websocket.send_json({"type": "ping"})
        except WebSocketDisconnect:
            pass
        except (ConnectionClosed, ConnectionClosedOK, ConnectionClosedError):
            log.debug("WebSocket client disconnected (keepalive or close)")
        except Exception as e:  # noqa: BLE001
            log.debug("WebSocket closed: %s", e)
        finally:
            orch.unsubscribe(queue)
    finally:
        reset_locale(token)
