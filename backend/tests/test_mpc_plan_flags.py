"""MPC plan_optimization flag."""

from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import MagicMock, patch

# PuLP is optional in production; provide a stub so MPCEngine can be imported.
if "pulp" not in sys.modules:
    pulp_stub = ModuleType("pulp")
    pulp_stub.LpProblem = MagicMock()
    pulp_stub.LpMinimize = 1
    pulp_stub.LpVariable = MagicMock()
    pulp_stub.lpSum = MagicMock()
    pulp_stub.PULP_CBC_CMD = MagicMock()
    pulp_stub.LpStatus = {1: "Optimal"}
    sys.modules["pulp"] = pulp_stub

from datetime import timedelta

from app.config import BatteryConfig, EngineConfig, GridChargeConfig, ReserveConfig
from app.engine.mpc import MPCEngine
from app.grid.reactive import ReactiveGrid
from app.models import ForecastBundle, LoadForecastPoint, SolarForecastPoint, Telemetry, utcnow


def _mpc() -> tuple[MPCEngine, ReactiveGrid]:
    battery = BatteryConfig(capacity_kwh=10.0, min_soc_floor=20.0, max_soc_ceiling=100.0)
    reserve = ReserveConfig(critical_load_w=400.0, min_autonomy_hours=12.0)
    reactive = ReactiveGrid(battery, reserve, GridChargeConfig())
    return MPCEngine(battery, reserve, EngineConfig(mpc_horizon_hours=6)), reactive


def _forecast() -> ForecastBundle:
    now = utcnow().replace(minute=0, second=0, microsecond=0)
    return ForecastBundle(
        solar=[SolarForecastPoint(ts=now, pv_power_w=0.0, pv_energy_wh=0.0)],
        load=[LoadForecastPoint(ts=now, load_power_w=500.0)],
    )


def test_mpc_optimization_disabled_skips_reserve_override():
    mpc, reactive = _mpc()
    telemetry = Telemetry(battery_soc=60.0, grid_present=False)
    forecast = _forecast()
    with patch.object(mpc, "_solve", return_value=(75.0, 0.0, True)):
        decision = mpc.decide(
            telemetry,
            forecast,
            None,
            None,
            shadow_mode=True,
            reactive=reactive,
            plan_optimization=False,
        )
    assert decision.reserve.target_soc == 60.0
    assert "has_mpc" not in decision.summary.params
