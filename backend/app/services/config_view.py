"""Redacted config serialization for API and MCP (never leak secrets)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..config import AppConfig


def config_view(cfg: AppConfig) -> dict:
    """Serialise config for the UI / agents, masking the HA token."""
    ha = cfg.ha.model_dump()
    ha["token"] = ""
    ha["has_token"] = bool(cfg.ha.token)
    data = {
        "ha": ha,
        "site": cfg.site.model_dump(),
        "battery": cfg.battery.model_dump(),
        "reserve": cfg.reserve.model_dump(),
        "forecast": cfg.forecast.model_dump(),
        "control": cfg.control.model_dump(),
        "fail_safe": cfg.fail_safe.model_dump(),
        "engine": cfg.engine.model_dump(),
        "inverter": cfg.inverter.model_dump(),
        "load_shedding": cfg.load_shedding.model_dump(),
        "grid_charge": cfg.grid_charge.model_dump(),
    }
    # Strip env-only secrets if echoed in nested config.
    forecast = data.get("forecast")
    if isinstance(forecast, dict):
        forecast.pop("solcast_api_key", None)
    return data
