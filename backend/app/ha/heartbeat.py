"""Home Assistant heartbeat for fail-safe staleness detection."""

from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from ..models import utcnow
from ..observability.metrics import metrics
from ..tz import to_site_local
from .client import HAClient, HAError

log = logging.getLogger("ha.heartbeat")


class HAHeartbeat:
    def __init__(self, ha: HAClient) -> None:
        self._ha = ha
        self.last_pulse_at: datetime | None = None

    def set_ha(self, ha: HAClient) -> None:
        self._ha = ha

    async def pulse(self, entity_id: str | None, *, site_tz: ZoneInfo) -> bool:
        """Update the HA input_datetime helper; non-fatal on failure."""
        if not entity_id or not entity_id.strip():
            return False
        entity_id = entity_id.strip()
        wall_clock = to_site_local(utcnow(), site_tz).strftime("%Y-%m-%d %H:%M:%S")
        try:
            await self._ha.call_service(
                "input_datetime",
                "set_datetime",
                {
                    "entity_id": entity_id,
                    "datetime": wall_clock,
                },
            )
        except HAError as e:
            metrics.heartbeat_failures += 1
            log.warning("Heartbeat pulse failed for %s: %s", entity_id, e)
            return False
        except Exception as e:  # noqa: BLE001
            metrics.heartbeat_failures += 1
            log.warning("Heartbeat pulse failed for %s: %s", entity_id, e)
            return False
        self.last_pulse_at = utcnow()
        metrics.heartbeat_pulses_total += 1
        return True
