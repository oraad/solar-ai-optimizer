"""Lightweight in-process counters for ops visibility."""

from __future__ import annotations

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

    def as_dict(self) -> dict[str, int]:
        return {k: int(v) for k, v in self.__dict__.items()}


metrics = Metrics()
