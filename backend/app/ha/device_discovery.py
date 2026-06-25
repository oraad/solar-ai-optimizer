"""Discover actionable companion entities on the same HA device as a power entity."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from pydantic import BaseModel

from ..i18n import t
from ..models import utcnow
from .client import HAClient

log = logging.getLogger("ha.device_discovery")

ACTIONABLE_DOMAINS = frozenset({
    "climate",
    "fan",
    "select",
    "input_select",
    "number",
    "input_number",
    "switch",
    "input_boolean",
})

_SKIP_ENTITY_CATEGORIES = frozenset({"diagnostic", "config"})

_REGISTRY_TTL = timedelta(seconds=60)
_DISCOVERY_TTL = timedelta(seconds=300)

_registry_cache: dict[int, tuple[datetime, list[dict[str, Any]]]] = {}
_discovery_cache: dict[int, dict[str, tuple[datetime, DeviceDiscoveryResult]]] = {}


class CompanionEntity(BaseModel):
    entity_id: str
    domain: str
    name: str | None = None


class DeviceDiscoveryResult(BaseModel):
    power_entity: str
    device_id: str | None = None
    companions: list[CompanionEntity] = []
    warning: str | None = None


def _client_key(ha: HAClient) -> int:
    return id(ha)


async def _entity_registry_list(ha: HAClient) -> list[dict[str, Any]]:
    key = _client_key(ha)
    now = utcnow()
    cached = _registry_cache.get(key)
    if cached and now - cached[0] < _REGISTRY_TTL:
        return cached[1]
    result = await ha.call_ws("config/entity_registry/list")
    entries = list(result or [])
    _registry_cache[key] = (now, entries)
    return entries


async def discover_device_companions(
    ha: HAClient, power_entity: str, *, use_cache: bool = True
) -> DeviceDiscoveryResult:
    """Return actionable entities on the same device, excluding the power entity."""
    key = _client_key(ha)
    now = utcnow()
    if use_cache:
        per_client = _discovery_cache.setdefault(key, {})
        hit = per_client.get(power_entity)
        if hit and now - hit[0] < _DISCOVERY_TTL:
            return hit[1]

    try:
        entry = await ha.call_ws(
            "config/entity_registry/get", entity_id=power_entity
        )
    except Exception as e:  # noqa: BLE001
        log.warning("entity_registry/get(%s) failed: %s", power_entity, e)
        return DeviceDiscoveryResult(
            power_entity=power_entity,
            warning=t("discovery.entity_not_in_registry", entity=power_entity),
        )

    device_id = (entry or {}).get("device_id")
    if not device_id:
        out = DeviceDiscoveryResult(
            power_entity=power_entity,
            device_id=None,
            warning=t("discovery.no_device_id"),
        )
        return out

    try:
        states = await ha.get_states()
    except Exception:  # noqa: BLE001
        states = []
    names = {
        s["entity_id"]: (s.get("attributes") or {}).get("friendly_name")
        for s in states
        if s.get("entity_id")
    }

    companions: list[CompanionEntity] = []
    for reg in await _entity_registry_list(ha):
        eid = reg.get("entity_id")
        if not eid or eid == power_entity:
            continue
        if reg.get("device_id") != device_id:
            continue
        if reg.get("disabled_by"):
            continue
        if reg.get("entity_category") in _SKIP_ENTITY_CATEGORIES:
            continue
        domain = eid.split(".", 1)[0] if "." in eid else ""
        if domain not in ACTIONABLE_DOMAINS:
            continue
        companions.append(
            CompanionEntity(
                entity_id=eid,
                domain=domain,
                name=names.get(eid) or reg.get("name") or eid,
            )
        )

    companions.sort(key=lambda c: c.entity_id)
    result = DeviceDiscoveryResult(
        power_entity=power_entity,
        device_id=device_id,
        companions=companions,
    )
    if use_cache:
        _discovery_cache.setdefault(key, {})[power_entity] = (now, result)
    return result
