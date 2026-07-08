"""MCP server entrypoint for stdio transport."""

from __future__ import annotations

import asyncio
import atexit
import logging
import sys

from .backends.api import ApiBackend
from .server import create_mcp_server

log = logging.getLogger("mcp")

_api_backend: ApiBackend | None = None


def _cleanup() -> None:
    global _api_backend
    if _api_backend is not None:
        try:
            asyncio.run(_api_backend.close())
        except Exception:  # noqa: BLE001
            pass
        _api_backend = None


def main() -> None:
    global _api_backend
    mode = sys.argv[1] if len(sys.argv) > 1 else "stdio"
    if mode != "stdio":
        log.error("Only stdio mode is supported from __main__; HTTP mounts on FastAPI.")
        sys.exit(1)

    _api_backend = ApiBackend()
    atexit.register(_cleanup)
    mcp = create_mcp_server(lambda: _api_backend, transport="stdio")
    mcp.run()


if __name__ == "__main__":
    main()
