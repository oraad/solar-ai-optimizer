"""FastAPI REST + WebSocket API."""

from .auth_routes import router as auth_router
from .debug_routes import router as debug_router
from .metrics import metrics_router
from .routes import router as api_router
from .system_update import router as system_update_router
from .ws import ws_router

__all__ = [
    "api_router",
    "auth_router",
    "debug_router",
    "metrics_router",
    "system_update_router",
    "ws_router",
]
