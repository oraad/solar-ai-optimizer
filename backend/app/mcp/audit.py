"""Structured audit logging for MCP tool invocations."""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Any, Iterator

from ..logging_setup import request_id_var

log = logging.getLogger("mcp.audit")


@contextmanager
def audit_tool_call(
    tool: str,
    *,
    transport: str,
    auth_mode: str = "bearer",
    args_keys: list[str] | None = None,
) -> Iterator[dict[str, Any]]:
    """Log MCP tool invocation; yield mutable result bag for error flag."""
    started = time.perf_counter()
    result: dict[str, Any] = {"error": False}
    rid = request_id_var.get()
    try:
        yield result
    finally:
        duration_ms = int((time.perf_counter() - started) * 1000)
        log.info(
            "mcp_tool tool=%s transport=%s auth=%s duration_ms=%s request_id=%s "
            "arg_keys=%s error=%s",
            tool,
            transport,
            auth_mode,
            duration_ms,
            rid,
            args_keys or [],
            result.get("error"),
        )
