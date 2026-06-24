"""Capture and restore HA entity state for load-shedding companions."""

from __future__ import annotations

import logging
from typing import Any

from ..adapters.ha_entity import _to_bool, is_entity_on
from ..ha.client import HAClient
from ..shed_snapshots import EntitySnapshot

log = logging.getLogger("ha.entity_restore")

_CLIMATE_ATTRS = (
    "hvac_mode",
    "temperature",
    "target_temp_high",
    "target_temp_low",
    "fan_mode",
)


def snapshot_from_ha_state(st: dict[str, Any] | None) -> EntitySnapshot | None:
    if not st:
        return None
    state = str(st.get("state", ""))
    attrs = dict(st.get("attributes") or {})
    domain = str(st.get("entity_id", "")).split(".", 1)[0]
    if domain == "climate":
        filtered = {k: attrs[k] for k in _CLIMATE_ATTRS if k in attrs}
        return EntitySnapshot(state=state, attributes=filtered)
    if domain == "fan" and "percentage" in attrs:
        return EntitySnapshot(state=state, attributes={"percentage": attrs["percentage"]})
    return EntitySnapshot(state=state, attributes={})


async def capture_entity_state(ha: HAClient, entity_id: str) -> EntitySnapshot | None:
    try:
        st = await ha.get_state(entity_id)
        return snapshot_from_ha_state(st)
    except Exception as e:  # noqa: BLE001
        log.debug("capture %s failed: %s", entity_id, e)
        return None


def _climate_was_off(snap: EntitySnapshot) -> bool:
    mode = snap.attributes.get("hvac_mode") or snap.state
    return str(mode).lower() in {"off", "unavailable", "unknown"}


async def restore_entity(
    ha: HAClient, entity_id: str, snap: EntitySnapshot
) -> None:
    domain = entity_id.split(".", 1)[0] if entity_id else ""

    if domain in {"switch", "input_boolean"}:
        on = _to_bool(snap.state)
        if on is not None:
            await ha.toggle_entity(entity_id, on)
        return

    if domain == "climate":
        if _climate_was_off(snap):
            await ha.call_service("climate", "turn_off", {"entity_id": entity_id})
            return
        mode = snap.attributes.get("hvac_mode") or snap.state
        if mode and str(mode).lower() not in {"off", "unavailable"}:
            await ha.call_service(
                "climate",
                "set_hvac_mode",
                {"entity_id": entity_id, "hvac_mode": mode},
            )
        temp = snap.attributes.get("temperature")
        if temp is not None:
            await ha.call_service(
                "climate",
                "set_temperature",
                {"entity_id": entity_id, "temperature": float(temp)},
            )
        fan = snap.attributes.get("fan_mode")
        if fan:
            await ha.call_service(
                "climate",
                "set_fan_mode",
                {"entity_id": entity_id, "fan_mode": fan},
            )
        return

    if domain == "select":
        await ha.select_option(entity_id, snap.state)
        return

    if domain == "input_select":
        await ha.call_service(
            "input_select",
            "select_option",
            {"entity_id": entity_id, "option": snap.state},
        )
        return

    if domain == "fan":
        if str(snap.state).lower() in {"off", "unavailable", "unknown"}:
            await ha.call_service("fan", "turn_off", {"entity_id": entity_id})
            return
        await ha.call_service("fan", "turn_on", {"entity_id": entity_id})
        pct = snap.attributes.get("percentage")
        if pct is not None:
            await ha.call_service(
                "fan",
                "set_percentage",
                {"entity_id": entity_id, "percentage": int(pct)},
            )
        return

    if domain == "number":
        await ha.set_number(entity_id, float(snap.state))
        return

    if domain == "input_number":
        await ha.call_service(
            "input_number",
            "set_value",
            {"entity_id": entity_id, "value": float(snap.state)},
        )
        return

    log.warning("restore_entity: unsupported domain %s for %s", domain, entity_id)


def power_entity_was_on(st: dict[str, Any] | None) -> bool:
    if not st:
        return False
    eid = st.get("entity_id", "")
    domain = str(eid).split(".", 1)[0] if eid else "switch"
    on = is_entity_on(domain, st.get("state"))
    if on is None:
        on = _to_bool(st.get("state"))
    return bool(on)
