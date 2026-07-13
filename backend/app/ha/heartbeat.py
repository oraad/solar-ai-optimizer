"""In-process liveness pulse for HA integration fail-safe (API heartbeat_last_pulse)."""

from __future__ import annotations

from datetime import datetime

from ..models import utcnow
from ..observability.metrics import metrics


class HAHeartbeat:
    """Advances last_pulse_at each control cycle; no Home Assistant entity write."""

    def __init__(self) -> None:
        self.last_pulse_at: datetime | None = None

    def pulse(self) -> bool:
        """Record a successful control-cycle liveness pulse."""
        self.last_pulse_at = utcnow()
        metrics.heartbeat_pulses_total += 1
        return True
