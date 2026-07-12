"""HA unit_of_measurement normalization."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.adapters.ha_entity import HAEntityAdapter
from app.config import InverterConfig, InverterReadMap, InverterWriteMap
from app.ha.units import (
    current_a_from_ha_state,
    ha_numeric_from_state,
    power_watts_from_ha_state,
    soc_pct_from_ha_state,
    temperature_c_from_ha_state,
)
from app.models import Capability


def _st(state: str, uom: str | None = None) -> dict:
    attrs: dict = {}
    if uom is not None:
        attrs["unit_of_measurement"] = uom
    return {"state": state, "attributes": attrs}


def test_power_watts_kw_and_w():
    assert power_watts_from_ha_state(_st("5.5", "kW")) == pytest.approx(5500.0)
    assert power_watts_from_ha_state(_st("5500", "W")) == pytest.approx(5500.0)
    assert power_watts_from_ha_state(_st("1200")) == pytest.approx(1200.0)


def test_temperature_f_to_c():
    assert temperature_c_from_ha_state(_st("68", "°F")) == pytest.approx(20.0)
    assert temperature_c_from_ha_state(_st("25", "°C")) == pytest.approx(25.0)
    assert temperature_c_from_ha_state(_st("21.5")) == pytest.approx(21.5)


def test_soc_percent():
    assert soc_pct_from_ha_state(_st("87", "%")) == pytest.approx(87.0)
    assert soc_pct_from_ha_state(_st("50")) == pytest.approx(50.0)


def test_current_ma_to_a():
    assert current_a_from_ha_state(_st("1500", "mA")) == pytest.approx(1.5)
    assert current_a_from_ha_state(_st("12", "A")) == pytest.approx(12.0)


def test_unknown_uom_treated_as_canonical():
    assert ha_numeric_from_state(_st("100", "banana"), kind="power") == pytest.approx(100.0)
    assert ha_numeric_from_state(_st("30", "K"), kind="temperature") == pytest.approx(30.0)


def test_unavailable_state():
    assert power_watts_from_ha_state(_st("unavailable", "kW")) is None
    assert temperature_c_from_ha_state(None) is None


def _adapter(*, invert: bool = False) -> HAEntityAdapter:
    ha = MagicMock()
    cfg = InverterConfig(
        read=InverterReadMap(
            pv_power="sensor.pv",
            load_power="sensor.load",
            battery_soc="sensor.soc",
            battery_power="sensor.battery_power",
            grid_power="sensor.grid",
            battery_temp="sensor.batt_temp",
        ),
        write=InverterWriteMap(max_grid_charge_current="number.charge_a"),
        invert_battery_power=invert,
    )
    return HAEntityAdapter(ha, cfg)


@pytest.mark.asyncio
async def test_read_telemetry_converts_kw_and_fahrenheit():
    adapter = _adapter(invert=False)
    adapter._ha.get_states = AsyncMock(
        return_value=[
            {"entity_id": "sensor.pv", "state": "2.5", "attributes": {"unit_of_measurement": "kW"}},
            {
                "entity_id": "sensor.load",
                "state": "1.2",
                "attributes": {"unit_of_measurement": "kW"},
            },
            {"entity_id": "sensor.soc", "state": "80", "attributes": {"unit_of_measurement": "%"}},
            {
                "entity_id": "sensor.battery_power",
                "state": "0.5",
                "attributes": {"unit_of_measurement": "kW"},
            },
            {
                "entity_id": "sensor.grid",
                "state": "800",
                "attributes": {"unit_of_measurement": "W"},
            },
            {
                "entity_id": "sensor.batt_temp",
                "state": "77",
                "attributes": {"unit_of_measurement": "°F"},
            },
        ]
    )
    t = await adapter.read_telemetry()
    assert t.pv_power == pytest.approx(2500.0)
    assert t.load_power == pytest.approx(1200.0)
    assert t.battery_soc == pytest.approx(80.0)
    assert t.battery_power == pytest.approx(500.0)
    assert t.grid_power == pytest.approx(800.0)
    assert t.battery_temp == pytest.approx(25.0)


@pytest.mark.asyncio
async def test_invert_applies_after_kw_conversion():
    adapter = _adapter(invert=True)
    adapter._ha.get_states = AsyncMock(
        return_value=[
            {
                "entity_id": "sensor.battery_power",
                "state": "0.5",
                "attributes": {"unit_of_measurement": "kW"},
            },
        ]
    )
    t = await adapter.read_telemetry()
    assert t.battery_power == pytest.approx(-500.0)


def test_telemetry_from_cache_converts_kw():
    adapter = _adapter(invert=False)
    adapter.update_cache(
        "sensor.pv",
        {"state": "3", "attributes": {"unit_of_measurement": "kW"}},
    )
    t = adapter.telemetry_from_cache()
    assert t.pv_power == pytest.approx(3000.0)


@pytest.mark.asyncio
async def test_read_capability_current_ma():
    adapter = _adapter()
    adapter._ha.get_state = AsyncMock(
        return_value={"state": "2500", "attributes": {"unit_of_measurement": "mA"}}
    )
    val = await adapter.read_capability(Capability.MAX_GRID_CHARGE_CURRENT)
    assert val == pytest.approx(2.5)
