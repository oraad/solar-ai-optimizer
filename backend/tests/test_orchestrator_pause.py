"""Paused engine must not apply shed or inverter writes."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models import BlackoutRisk, Decision, Override, ReserveTarget, utcnow
from tests.conftest import DUMMY_MSG


def _decision_with_shed() -> Decision:
    from app.models import ShedAction

    return Decision(
        ts=utcnow(),
        reserve=ReserveTarget(
            target_soc=50,
            solar_bridge_soc=55,
            autonomy_floor_soc=30,
            rationale=DUMMY_MSG,
        ),
        actions=[],
        shed_actions=[
            ShedAction(
                tier="pool",
                entity="switch.pool",
                desired_on=False,
                reason=DUMMY_MSG,
            )
        ],
        blackout_risk=BlackoutRisk.LOW,
        blackout_risk_score=0.1,
        summary=DUMMY_MSG,
        shadow_mode=True,
    )


@pytest.mark.asyncio
async def test_paused_skips_executor_and_shed(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 't.db'}")
    from app.config import get_settings
    from app.config_store import ConfigStore
    from app.orchestrator import Orchestrator

    settings = get_settings()
    (tmp_path / "base.yaml").write_text("battery:\n  capacity_kwh: 10\n")
    store = ConfigStore(str(tmp_path / "base.yaml"), str(tmp_path / "runtime.yaml"))
    orch = Orchestrator(settings, store)

    orch.paused = True
    orch.collector = MagicMock()
    orch.collector.sample = AsyncMock(
        return_value=MagicMock(grid_present=False, battery_soc=40.0, ts=utcnow())
    )
    orch.executor = MagicMock()
    orch.executor.apply_decision = AsyncMock(return_value=[])
    orch.executor.apply_shed_actions = AsyncMock(return_value=[])
    orch.forecast = MagicMock()
    orch.forecast.current = None
    orch.reactive = MagicMock()
    orch.reactive.compute_stats = AsyncMock(return_value=MagicMock())
    orch._decide = MagicMock(return_value=_decision_with_shed())
    orch._broadcast = AsyncMock()

    monkeypatch.setattr("app.orchestrator.repo.save_decision", AsyncMock())

    await orch.control_cycle()

    orch.executor.apply_decision.assert_not_called()
    orch.executor.apply_shed_actions.assert_not_called()
    assert orch.latest_results == []
    assert orch.latest_shed_results == []
