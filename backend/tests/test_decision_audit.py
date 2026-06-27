"""Decision history deduplication: skip save when audit payload unchanged."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models import (
    BlackoutRisk,
    Capability,
    ControlAction,
    Decision,
    Msg,
    ReserveTarget,
    ShedAction,
    utcnow,
)
from app.storage.repo import decisions_audit_equal
from tests.conftest import DUMMY_MSG


def _sample_decision(**overrides) -> Decision:
    base = Decision(
        ts=utcnow(),
        reserve=ReserveTarget(
            target_soc=50.0,
            solar_bridge_soc=55.0,
            autonomy_floor_soc=30.0,
            rationale=DUMMY_MSG,
        ),
        actions=[
            ControlAction(
                capability=Capability.GRID_CHARGE_ENABLE,
                value=True,
                reason=DUMMY_MSG,
                priority=100,
            )
        ],
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
    for key, value in overrides.items():
        setattr(base, key, value)
    return base


def test_decisions_audit_equal_none_prev() -> None:
    assert decisions_audit_equal(None, _sample_decision()) is False


def test_decisions_audit_equal_same_except_ts() -> None:
    a = _sample_decision(ts=utcnow())
    b = _sample_decision(ts=utcnow() + timedelta(seconds=30))
    assert decisions_audit_equal(a, b) is True


@pytest.mark.parametrize(
    ("mutator",),
    [
        (lambda d: setattr(d.reserve, "target_soc", 60.0),),
        (lambda d: setattr(d, "blackout_risk", BlackoutRisk.HIGH),),
        (lambda d: setattr(d, "blackout_risk_score", 0.9),),
        (lambda d: setattr(d, "shadow_mode", False),),
        (
            lambda d: setattr(
                d,
                "summary",
                Msg(key="engine.summary.shedding_only"),
            ),
        ),
        (
            lambda d: setattr(
                d.reserve,
                "rationale",
                Msg(key="engine.reserve.main", params={"driver": "x"}),
            ),
        ),
        (
            lambda d: d.actions.__setitem__(
                0,
                ControlAction(
                    capability=Capability.MAX_GRID_CHARGE_CURRENT,
                    value=40.0,
                    reason=DUMMY_MSG,
                ),
            ),
        ),
        (
            lambda d: d.shed_actions.__setitem__(
                0,
                ShedAction(
                    tier="ac",
                    entity="switch.ac",
                    desired_on=True,
                    reason=DUMMY_MSG,
                ),
            ),
        ),
    ],
)
def test_decisions_audit_equal_detects_change(mutator) -> None:
    a = _sample_decision()
    b = _sample_decision()
    mutator(b)
    assert decisions_audit_equal(a, b) is False


@pytest.mark.asyncio
async def test_control_cycle_skips_save_when_unchanged(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 't.db'}")
    from app.config import get_settings
    from app.config_store import ConfigStore
    from app.orchestrator import Orchestrator

    settings = get_settings()
    (tmp_path / "base.yaml").write_text("battery:\n  capacity_kwh: 10\n")
    store = ConfigStore(str(tmp_path / "base.yaml"), str(tmp_path / "runtime.yaml"))
    orch = Orchestrator(settings, store)

    decision = _sample_decision()
    orch.collector = MagicMock()
    orch.collector.sample = AsyncMock(
        return_value=MagicMock(grid_present=True, battery_soc=50.0, ts=utcnow())
    )
    orch.executor = MagicMock()
    orch.executor.apply_decision = AsyncMock(return_value=[])
    orch.executor.apply_shed_actions = AsyncMock(return_value=[])
    orch.forecast = MagicMock()
    orch.forecast.current = None
    orch.reactive = MagicMock()
    orch.reactive.compute_stats = AsyncMock(return_value=MagicMock())
    orch._decide = MagicMock(return_value=decision)
    orch._broadcast = AsyncMock()

    save_mock = AsyncMock()
    monkeypatch.setattr("app.orchestrator.repo.save_decision", save_mock)

    await orch.control_cycle()
    await orch.control_cycle()

    save_mock.assert_called_once()


@pytest.mark.asyncio
async def test_control_cycle_saves_when_decision_changes(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 't.db'}")
    from app.config import get_settings
    from app.config_store import ConfigStore
    from app.orchestrator import Orchestrator

    settings = get_settings()
    (tmp_path / "base.yaml").write_text("battery:\n  capacity_kwh: 10\n")
    store = ConfigStore(str(tmp_path / "base.yaml"), str(tmp_path / "runtime.yaml"))
    orch = Orchestrator(settings, store)

    first = _sample_decision()
    second = _sample_decision()
    second.reserve.target_soc = 65.0

    orch.collector = MagicMock()
    orch.collector.sample = AsyncMock(
        return_value=MagicMock(grid_present=True, battery_soc=50.0, ts=utcnow())
    )
    orch.executor = MagicMock()
    orch.executor.apply_decision = AsyncMock(return_value=[])
    orch.executor.apply_shed_actions = AsyncMock(return_value=[])
    orch.forecast = MagicMock()
    orch.forecast.current = None
    orch.reactive = MagicMock()
    orch.reactive.compute_stats = AsyncMock(return_value=MagicMock())
    orch._decide = MagicMock(side_effect=[first, second])
    orch._broadcast = AsyncMock()

    save_mock = AsyncMock()
    monkeypatch.setattr("app.orchestrator.repo.save_decision", save_mock)

    await orch.control_cycle()
    await orch.control_cycle()

    assert save_mock.call_count == 2
