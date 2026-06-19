"""HA entity adapter telemetry normalization."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.adapters.ha_entity import HAEntityAdapter
from app.config import InverterConfig, InverterReadMap


def _adapter(*, invert: bool = False, battery_power: str = "sensor.battery_power") -> HAEntityAdapter:
    ha = MagicMock()
    cfg = InverterConfig(
        read=InverterReadMap(battery_power=battery_power),
        invert_battery_power=invert,
    )
    return HAEntityAdapter(ha, cfg)


@pytest.mark.asyncio
async def test_read_telemetry_inverts_battery_power():
    adapter = _adapter(invert=True)
    adapter._ha.get_states = AsyncMock(
        return_value=[
            {"entity_id": "sensor.battery_power", "state": "500", "attributes": {}},
        ]
    )
    t = await adapter.read_telemetry()
    assert t.battery_power == -500.0


@pytest.mark.asyncio
async def test_read_telemetry_no_invert():
    adapter = _adapter(invert=False)
    adapter._ha.get_states = AsyncMock(
        return_value=[
            {"entity_id": "sensor.battery_power", "state": "500", "attributes": {}},
        ]
    )
    t = await adapter.read_telemetry()
    assert t.battery_power == 500.0


def test_telemetry_from_cache_inverts_battery_power():
    adapter = _adapter(invert=True)
    adapter.update_cache("sensor.battery_power", {"state": "250", "attributes": {}})
    t = adapter.telemetry_from_cache()
    assert t.battery_power == -250.0
