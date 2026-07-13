"""Lightweight in-process counters for ops visibility."""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class Metrics:
    control_cycles: int = 0
    control_cycle_failures: int = 0
    executor_writes_applied: int = 0
    executor_writes_skipped: int = 0
    shed_writes_applied: int = 0
    shed_writes_skipped: int = 0
    forecast_refresh_failures: int = 0
    mpc_fallbacks: int = 0
    ha_ws_restarts: int = 0
    heartbeat_pulses_total: int = 0
    heartbeat_failures: int = 0
    mcp_tool_calls_total: int = 0
    mcp_auth_failures_total: int = 0
    mcp_simulate_calls_total: int = 0
    # Process start time (unix epoch seconds); excluded from as_dict() since it
    # is a gauge/timestamp, not a counter, and exposed separately in /metrics.
    process_start_time: float = field(default_factory=time.time)

    def as_dict(self) -> dict[str, int]:
        return {
            k: int(v) for k, v in self.__dict__.items() if k != "process_start_time"
        }


metrics = Metrics()
