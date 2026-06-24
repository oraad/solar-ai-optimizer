"""Entity restore helpers."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from app.ha.entity_restore import power_entity_was_on, restore_entity
from app.shed_snapshots import EntitySnapshot


def test_power_entity_was_on_climate():
    assert power_entity_was_on({"entity_id": "climate.x", "state": "cool"}) is True
    assert power_entity_was_on({"entity_id": "climate.x", "state": "off"}) is False


def test_restore_select():
    ha = MagicMock()
    ha.select_option = AsyncMock()

    async def run() -> None:
        await restore_entity(
            ha,
            "select.fan_mode",
            EntitySnapshot(state="high", attributes={}),
        )
        ha.select_option.assert_awaited_once_with("select.fan_mode", "high")

    asyncio.run(run())
