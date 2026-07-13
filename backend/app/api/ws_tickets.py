"""Short-lived one-time WebSocket tickets (avoid putting long-lived tokens in URLs)."""

from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass

from ..config import Settings
from .session import SessionUser

# ticket -> (expires_at, session snapshot fields)
_TICKET_TTL_SECONDS = 30
_lock = threading.Lock()


@dataclass(frozen=True)
class _TicketEntry:
    expires_at: float
    user: SessionUser
    jti: str | None = None


_tickets: dict[str, _TicketEntry] = {}


def _purge_locked(now: float) -> None:
    expired = [k for k, v in _tickets.items() if v.expires_at <= now]
    for k in expired:
        del _tickets[k]


def mint_ws_ticket(
    user: SessionUser,
    settings: Settings | None = None,
    jti: str | None = None,
) -> dict[str, str | int]:
    """Mint a single-use ticket for the authenticated session.

    When `jti` (the session cookie's token id) is supplied, the ticket is
    tied to that session: logging out revokes the jti and drops any tickets
    minted for it via `drop_tickets_for_jti`, so a stolen ticket can't
    outlive the session that minted it.
    """
    _ = settings
    token = secrets.token_urlsafe(24)
    now = time.time()
    with _lock:
        _purge_locked(now)
        _tickets[token] = _TicketEntry(
            expires_at=now + _TICKET_TTL_SECONDS, user=user, jti=jti
        )
    return {"ticket": token, "expires_in": _TICKET_TTL_SECONDS}


def consume_ws_ticket(ticket: str) -> SessionUser | None:
    """Consume a ticket (single-use). Returns the SessionUser or None."""
    if not ticket:
        return None
    now = time.time()
    with _lock:
        _purge_locked(now)
        entry = _tickets.pop(ticket, None)
    if entry is None or entry.expires_at <= now:
        return None
    if entry.jti is not None:
        # Lazy import: session.py lazily imports this module too, to avoid a
        # hard import cycle at module load time.
        from .session import _is_jti_revoked

        if _is_jti_revoked(entry.jti):
            return None
    return entry.user


def drop_tickets_for_jti(jti: str) -> None:
    """Invalidate any outstanding tickets minted for a now-revoked session."""
    if not jti:
        return
    with _lock:
        stale = [k for k, v in _tickets.items() if v.jti == jti]
        for k in stale:
            del _tickets[k]
