"""Device companion discovery filtering."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from app.ha.device_discovery import discover_device_companions


def test_skips_power_entity_and_non_actionable():
    ha = MagicMock()
    ha.call_ws = AsyncMock(
        side_effect=[
            {"entity_id": "switch.ac", "device_id": "dev1"},
            [
                {"entity_id": "switch.ac", "device_id": "dev1"},
                {"entity_id": "climate.room", "device_id": "dev1"},
                {"entity_id": "sensor.temp", "device_id": "dev1"},
                {
                    "entity_id": "select.mode",
                    "device_id": "dev1",
                    "entity_category": "config",
                },
            ],
        ]
    )
    ha.get_states = AsyncMock(
        return_value=[
            {
                "entity_id": "climate.room",
                "state": "cool",
                "attributes": {"friendly_name": "Room AC"},
            },
        ]
    )

    async def run() -> None:
        result = await discover_device_companions(ha, "switch.ac", use_cache=False)
        assert result.device_id == "dev1"
        assert [c.entity_id for c in result.companions] == ["climate.room"]

    asyncio.run(run())


def test_no_device_id_returns_warning():
    ha = MagicMock()
    ha.call_ws = AsyncMock(return_value={"entity_id": "switch.orphan", "device_id": None})

    async def run() -> None:
        result = await discover_device_companions(ha, "switch.orphan", use_cache=False)
        assert result.companions == []
        assert result.warning

    asyncio.run(run())
