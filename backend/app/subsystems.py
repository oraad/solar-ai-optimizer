"""Subsystem enable/pause helpers and deployment profile labels."""

from __future__ import annotations

from .config import AppConfig


def deployment_profile(cfg: AppConfig) -> str:
    if (
        cfg.load_shedding.enabled
        and not cfg.grid_charge.enabled
        and not cfg.engine.enabled
    ):
        return "shed_primary"
    if (
        cfg.load_shedding.enabled
        and not cfg.grid_charge.enabled
        and cfg.engine.enabled
    ):
        return "shed_advisory"
    if (
        cfg.load_shedding.enabled
        or not cfg.grid_charge.enabled
        or not cfg.engine.enabled
    ):
        return "custom"
    return "full"


def plan_optimization(cfg: AppConfig) -> bool:
    return cfg.engine.enabled


def plan_grid_charge(cfg: AppConfig) -> bool:
    return cfg.grid_charge.enabled and cfg.engine.enabled


def plan_shedding(cfg: AppConfig) -> bool:
    return cfg.load_shedding.enabled
