"""Normalize HA power sensor states to watts.

Re-exports from ``app.ha.units`` for backward-compatible imports.
"""

from __future__ import annotations

from .units import effective_max_grid_charge_a, power_watts_from_ha_state

__all__ = ["effective_max_grid_charge_a", "power_watts_from_ha_state"]
