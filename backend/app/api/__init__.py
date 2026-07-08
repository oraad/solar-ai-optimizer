"""FastAPI REST + WebSocket API."""

from .auth_routes import router as auth_router
from .debug_routes import router as debug_router
from .ha_oauth_routes import router as ha_oauth_router
from .metrics import metrics_router
from .pair_routes import router as pair_router
from .routes import router as api_router
from .system_update import router as system_update_router
from .ws import ws_router

__all__ = [
    "api_router",
    "auth_router",
    "debug_router",
    "ha_oauth_router",
    "metrics_router",
    "pair_router",
    "system_update_router",
    "ws_router",
]
