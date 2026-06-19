"""MPC solver feasibility reporting (no I/O)."""

from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import MagicMock

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

from app.config import BatteryConfig, EngineConfig, ReserveConfig  # noqa: E402
from app.engine.mpc import MPCEngine  # noqa: E402
from app.models import ForecastBundle  # noqa: E402


def _mpc() -> MPCEngine:
    battery = BatteryConfig(capacity_kwh=10.0, min_soc_floor=20.0, max_soc_ceiling=100.0)
    reserve = ReserveConfig(critical_load_w=400.0, min_autonomy_hours=12.0)
    return MPCEngine(battery, reserve, EngineConfig(mpc_horizon_hours=6))


def test_solve_empty_forecast_not_feasible():
    mpc = _mpc()
    reserve, unserved, feasible = mpc._solve(None, None)  # noqa: SLF001
    assert reserve is None
    assert unserved == 0.0
    assert feasible is False

