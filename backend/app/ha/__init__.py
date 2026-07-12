"""Home Assistant clients (REST service calls + WebSocket state stream)."""

from .client import HAAuthInvalid, HAClient, HAError, WsErrorClass, classify_ws_error

__all__ = [
    "HAAuthInvalid",
    "HAClient",
    "HAError",
    "WsErrorClass",
    "classify_ws_error",
]
