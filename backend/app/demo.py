"""Synthetic data for DEMO_MODE (documentation screenshots only)."""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from .i18n import msg
from .i18n.skip_keys import SKIP_SHADOW_MODE
from .models import (
    BlackoutRisk,
    Capability,
    ControlAction,
    Decision,
    ExecutionResult,
    GridEvent,
    ReserveTarget,
    ShedResult,
    Telemetry,
    utcnow,
)

# Cape Town — good solar profile for demo forecasts (Open-Meteo).
DEMO_LATITUDE = -33.9249
DEMO_LONGITUDE = 18.4241


def synthetic_telemetry(ts: datetime | None = None) -> Telemetry:
    """Realistic midday-ish snapshot with diurnal PV curve."""
    now = ts or utcnow()
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    hour = now.hour + now.minute / 60.0
    solar_hour = (hour + 2) % 24
    pv_factor = max(0.0, math.sin((solar_hour - 6) * math.pi / 12))
    pv_power = round(4200 * pv_factor, 0)
    load_power = 850.0 + 150.0 * math.sin(hour * math.pi / 12)
    battery_soc = 62.0 + 8.0 * math.sin((hour - 8) * math.pi / 16)
    battery_soc = max(35.0, min(88.0, battery_soc))
    battery_power = round((pv_power - load_power) * 0.6, 0)
    grid_power = round(max(0.0, load_power - pv_power - battery_power * 0.5), 0)
    return Telemetry(
        ts=now,
        pv_power=pv_power,
        load_power=round(load_power, 0),
        battery_soc=round(battery_soc, 1),
        battery_power=battery_power,
        grid_power=grid_power,
        grid_present=True,
        battery_temp=28.5,
        outdoor_temp=22.0 + 4.0 * math.sin((hour - 9) * math.pi / 12),
    )


def demo_config_overrides() -> dict:
    """Runtime config patch for a populated Settings panel and forecasts."""
    return {
        "ha": {
            "base_url": "http://homeassistant.local:8123",
            "token": "demo-token-not-real",
            "verify_ssl": True,
        },
        "site": {
            "timezone": "Africa/Johannesburg",
            "latitude": DEMO_LATITUDE,
            "longitude": DEMO_LONGITUDE,
        },
        "forecast": {
            "arrays": [
                {
                    "name": "North roof",
                    "kwp": 5.0,
                    "tilt": 18.0,
                    "azimuth": 360.0,
                }
            ],
            "temperature": {
                "enabled": True,
                "ha_entity": "sensor.demo_outdoor_temperature",
            },
        },
        "inverter": {
            "read": {
                "pv_power": "sensor.demo_pv_power",
                "load_power": "sensor.demo_load_power",
                "battery_soc": "sensor.demo_battery_soc",
                "battery_power": "sensor.demo_battery_power",
                "grid_power": "sensor.demo_grid_power",
                "grid_present": "binary_sensor.demo_grid_present",
                "battery_temp": "sensor.demo_battery_temperature",
            },
            "write": {
                "grid_charge_enable": "switch.demo_grid_charge",
                "max_grid_charge_current": "number.demo_max_grid_charge_current",
            },
        },
        "load_shedding": {
            "enabled": True,
            "restore_all_when_grid_present": True,
            "tiers": [
                {
                    "name": "Pool",
                    "priority": 1,
                    "shed_below_soc": 45.0,
                    "restore_above_soc": 55.0,
                    "switches": [
                        "switch.demo_pool_pump",
                        "switch.demo_pool_heater",
                    ],
                }
            ],
        },
        "fail_safe": {
            "heartbeat_entity": "input_datetime.solar_optimizer_heartbeat",
            "heartbeat_enabled": True,
            "shutdown_failsafe_enabled": True,
        },
    }


def demo_decision(ts: datetime | None = None, shadow_mode: bool = True) -> Decision:
    """Readable decision for Overview / History screenshots."""
    now = ts or utcnow()
    return Decision(
        ts=now,
        reserve=ReserveTarget(
            target_soc=52.0,
            solar_bridge_soc=48.0,
            autonomy_floor_soc=44.0,
            rationale=msg(
                "engine.grid.legacy_top_up",
                soc=52,
                target=52,
            ),
        ),
        actions=[
            ControlAction(
                capability=Capability.GRID_CHARGE_ENABLE,
                value=True,
                reason=msg("engine.grid.ramp_to", soc=52, target=52, amps=40),
            ),
            ControlAction(
                capability=Capability.MAX_GRID_CHARGE_CURRENT,
                value=40.0,
                reason=msg("engine.grid.charge_hard", amps=40),
            ),
        ],
        blackout_risk=BlackoutRisk.LOW,
        blackout_risk_score=0.12,
        summary=msg(
            "engine.summary.with_priorities_present",
            order="resilience → savings → self-sufficiency",
            soc="52",
            target=52,
            risk="low",
            extra="",
            advisory_suffix="",
            advisory_kw=0,
        ),
        shadow_mode=shadow_mode,
    )


def demo_execution(ts: datetime | None = None) -> ExecutionResult:
    now = ts or utcnow()
    return ExecutionResult(
        capability=Capability.GRID_CHARGE_ENABLE,
        requested=True,
        applied=False,
        verified=False,
        skipped_reason=SKIP_SHADOW_MODE,
        ts=now,
    )


def demo_shed_execution(ts: datetime | None = None) -> ShedResult:
    now = ts or utcnow()
    return ShedResult(
        tier="Pool",
        entity="switch.demo_pool_pump",
        desired_on=True,
        applied=False,
        verified=False,
        skipped_reason=SKIP_SHADOW_MODE,
        ts=now,
    )


def historical_telemetry_series(
    days: int = 7, interval_minutes: int = 15
) -> list[Telemetry]:
    """Generate telemetry rows for History charts."""
    end = utcnow()
    start = end - timedelta(days=days)
    points: list[Telemetry] = []
    step = timedelta(minutes=interval_minutes)
    t = start
    while t <= end:
        points.append(synthetic_telemetry(t))
        t += step
    return points


def historical_grid_events(days: int = 7) -> list[GridEvent]:
    """A few grid transitions for the History grid-events tab."""
    end = utcnow()
    events = [
        GridEvent(ts=end - timedelta(days=2, hours=14), grid_present=False),
        GridEvent(ts=end - timedelta(days=2, hours=16, minutes=22), grid_present=True),
        GridEvent(ts=end - timedelta(days=5, hours=3), grid_present=False),
        GridEvent(ts=end - timedelta(days=5, hours=5, minutes=10), grid_present=True),
    ]
    return [e for e in events if e.ts >= end - timedelta(days=days)]
