"""Orchestrator grid charge ramp state tracking."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.models import (
    Capability,
    ExecutionResult,
    GridChargePlan,
)
from app.orchestrator import Orchestrator


def _bare_orch() -> Orchestrator:
    """Orchestrator instance without running __init__ (avoids HA client setup)."""
    orch = object.__new__(Orchestrator)
    orch._last_grid_charge_amps = None
    orch.shadow_mode = False
    orch.engine = MagicMock()
    orch.latest_decision = None
    return orch


def test_update_last_amps_on_already_set_skip() -> None:
    orch = _bare_orch()
    orch.latest_decision = MagicMock(
        grid_charge=GridChargePlan(
            enabled=True,
            target_amps=30.0,
            max_amps=60.0,
            rationale="test",
        )
    )
    orch._update_last_grid_charge_amps(
        [
            ExecutionResult(
                capability=Capability.MAX_GRID_CHARGE_CURRENT,
                requested=30.0,
                applied=False,
                verified=False,
                skipped_reason="already set",
            )
        ]
    )
    assert orch._last_grid_charge_amps == 30.0
    orch.engine.set_last_grid_charge_amps.assert_called_once_with(30.0)


def test_update_last_amps_from_shadow_plan() -> None:
    orch = _bare_orch()
    orch.shadow_mode = True
    orch.latest_decision = MagicMock(
        grid_charge=GridChargePlan(
            enabled=True,
            target_amps=25.0,
            max_amps=60.0,
            rationale="shadow ramp",
        )
    )
    orch._update_last_grid_charge_amps([])
    assert orch._last_grid_charge_amps == 25.0
    orch.engine.set_last_grid_charge_amps.assert_called_once_with(25.0)
