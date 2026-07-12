"""Normalize HA sensor states to canonical app units via unit_of_measurement."""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from typing import Any, Literal

log = logging.getLogger("ha.units")

NumericKind = Literal["power", "temperature", "soc", "current"]

_WATT_UNITS = frozenset({"w", "watt", "watts"})
_KW_UNITS = frozenset({"kw", "kilowatt", "kilowatts"})
_CELSIUS_UNITS = frozenset({"c", "degc", "degreecelsius", "degreescelsius", "celsius"})
_FAHRENHEIT_UNITS = frozenset(
    {"f", "degf", "degreefahrenheit", "degreesfahrenheit", "fahrenheit"}
)
_PERCENT_UNITS = frozenset({"%", "percent", "percentage"})
_AMP_UNITS = frozenset({"a", "amp", "amps", "ampere", "amperes"})
_MA_UNITS = frozenset({"ma", "milliamp", "milliamps", "milliampere", "milliamperes"})

# Strip spaces and normalize unicode degree / micro prefixes for matching.
_UOM_CLEAN = re.compile(r"[\s\u00b0]+")


def _normalize_uom(raw: Any) -> str:
    s = str(raw or "").strip().lower()
    if not s:
        return ""
    # Keep leading ° by mapping common forms before strip of degree char alone
    s = s.replace("°", "").replace("º", "")
    s = _UOM_CLEAN.sub("", s)
    return s


def _parse_state_value(st: Mapping[str, Any] | None) -> float | None:
    if not st or not isinstance(st, Mapping):
        return None
    raw = st.get("state")
    if raw is None or raw in ("unknown", "unavailable", ""):
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _uom_from_state(st: Mapping[str, Any]) -> str:
    attrs = st.get("attributes") or {}
    if not isinstance(attrs, Mapping):
        return ""
    return _normalize_uom(attrs.get("unit_of_measurement"))


def coerce_ha_state(st: Any) -> dict[str, Any] | None:
    """Accept a full HA state dict or a bare state value for conversion."""
    if st is None:
        return None
    if isinstance(st, Mapping):
        return dict(st)
    return {"state": st, "attributes": {}}


def ha_numeric_from_state(
    state: Mapping[str, Any] | None,
    *,
    kind: NumericKind,
) -> float | None:
    """Parse HA state to canonical units using attributes.unit_of_measurement.

    Canonical outputs: power→W, temperature→°C, soc→%, current→A.
    Missing or unknown UoM is treated as already-canonical (backward compatible).
    """
    if not state or not isinstance(state, Mapping):
        return None
    value = _parse_state_value(state)
    if value is None:
        return None
    uom = _uom_from_state(state)
    attrs = state.get("attributes") or {}
    raw_uom = attrs.get("unit_of_measurement") if isinstance(attrs, Mapping) else None

    if kind == "power":
        return _to_watts(value, uom, raw_uom)
    if kind == "temperature":
        return _to_celsius(value, uom, raw_uom)
    if kind == "soc":
        return _to_percent(value, uom, raw_uom)
    if kind == "current":
        return _to_amps(value, uom, raw_uom)
    raise ValueError(f"unsupported numeric kind: {kind!r}")


def _to_watts(value: float, uom: str, raw_uom: Any) -> float:
    if uom in _KW_UNITS:
        return value * 1000.0
    if uom in _WATT_UNITS or not uom:
        if not uom:
            log.debug("power entity missing unit_of_measurement; treating as watts")
        return value
    log.warning(
        "Unrecognized power unit_of_measurement %r; treating numeric state as watts",
        raw_uom,
    )
    return value


def _to_celsius(value: float, uom: str, raw_uom: Any) -> float:
    if uom in _FAHRENHEIT_UNITS:
        return (value - 32.0) * 5.0 / 9.0
    if uom in _CELSIUS_UNITS or not uom:
        if not uom:
            log.debug("temperature entity missing unit_of_measurement; treating as °C")
        return value
    log.warning(
        "Unrecognized temperature unit_of_measurement %r; treating numeric state as °C",
        raw_uom,
    )
    return value


def _to_percent(value: float, uom: str, raw_uom: Any) -> float:
    if uom in _PERCENT_UNITS or not uom:
        if not uom:
            log.debug("soc entity missing unit_of_measurement; treating as percent")
        return value
    log.warning(
        "Unrecognized soc unit_of_measurement %r; treating numeric state as percent",
        raw_uom,
    )
    return value


def _to_amps(value: float, uom: str, raw_uom: Any) -> float:
    if uom in _MA_UNITS:
        return value / 1000.0
    if uom in _AMP_UNITS or not uom:
        if not uom:
            log.debug("current entity missing unit_of_measurement; treating as amps")
        return value
    log.warning(
        "Unrecognized current unit_of_measurement %r; treating numeric state as amps",
        raw_uom,
    )
    return value


def power_watts_from_ha_state(st: dict[str, Any] | None) -> float | None:
    """Parse HA state to watts using attributes.unit_of_measurement."""
    return ha_numeric_from_state(st, kind="power")


def temperature_c_from_ha_state(st: Mapping[str, Any] | None) -> float | None:
    return ha_numeric_from_state(st, kind="temperature")


def soc_pct_from_ha_state(st: Mapping[str, Any] | None) -> float | None:
    return ha_numeric_from_state(st, kind="soc")


def current_a_from_ha_state(st: Mapping[str, Any] | None) -> float | None:
    return ha_numeric_from_state(st, kind="current")


def ha_numeric_from_any(st: Any, *, kind: NumericKind) -> float | None:
    """Convert a cache entry or HA state dict to canonical units."""
    return ha_numeric_from_state(coerce_ha_state(st), kind=kind)


def effective_max_grid_charge_a(
    *,
    max_grid_charge_a: float,
    nominal_voltage: float,
    site_import_w: float | None,
) -> float:
    """Planning ceiling: min(inverter max A, site import W / V)."""
    max_a = max(0.0, float(max_grid_charge_a))
    if site_import_w is None:
        return max_a
    v = max(float(nominal_voltage), 1.0)
    from_import = max(0.0, float(site_import_w)) / v
    return min(max_a, from_import)
