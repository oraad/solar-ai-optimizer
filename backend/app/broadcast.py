"""WebSocket broadcast fan-out for live status updates.

Extracted from Orchestrator so that subscriber management and fan-out
logic can live independently. The Orchestrator holds a ``StatusBroadcaster``
instance and delegates ``subscribe()``, ``unsubscribe()``, and ``_broadcast()``
to it.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Callable

log = logging.getLogger("broadcast")


class StatusBroadcaster:
    """Manage a set of asyncio.Queue subscribers and fan out payloads to them.

    Args:
        get_payload: Callable that returns the dict payload to broadcast.
                     Typically a bound method on the Orchestrator that calls
                     ``build_status()`` and serialises the result.
    """

    def __init__(self, get_payload: Callable[[], dict]) -> None:
        self._subscribers: set[asyncio.Queue] = set()
        self._get_payload = get_payload

    def subscribe(self) -> asyncio.Queue:
        """Register a new subscriber; returns the queue to read from."""
        q: asyncio.Queue = asyncio.Queue(maxsize=8)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        """Remove a subscriber queue."""
        self._subscribers.discard(q)

    async def broadcast(self) -> None:
        """Build the current payload and push it to all subscribers.

        Drops the oldest item from a full queue rather than blocking, and
        silently removes queues that raise unexpected errors.
        """
        if not self._subscribers:
            return
        payload = self._get_payload()
        for q in list(self._subscribers):
            try:
                if q.full():
                    _ = q.get_nowait()
                q.put_nowait(payload)
            except Exception:  # noqa: BLE001
                self._subscribers.discard(q)
