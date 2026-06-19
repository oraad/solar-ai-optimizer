"""FastAPI REST + WebSocket API."""

from .auth_routes import router as auth_router
from .metrics import metrics_router
from .routes import router as api_router
from .ws import ws_router

__all__ = ["api_router", "auth_router", "metrics_router", "ws_router"]
