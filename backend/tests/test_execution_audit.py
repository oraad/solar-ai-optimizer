"""Execution and shed audit deduplication: skip save when audit payload unchanged."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.config import BatteryConfig, ControlConfig
from app.control.executor import Executor
from app.i18n.skip_keys import SKIP_ALREADY_SET, SKIP_SHADOW_MODE
from app.models import Capability, ExecutionResult, ShedResult, utcnow
from app.storage.repo import executions_audit_equal, shed_executions_audit_equal


def _sample_execution(**overrides) -> ExecutionResult:
    base = ExecutionResult(
        capability=Capability.MAX_GRID_CHARGE_CURRENT,
        requested=32.0,
        applied=False,
        verified=False,
        skipped_reason=SKIP_ALREADY_SET,
    )
    for key, value in overrides.items():
        setattr(base, key, value)
    return base


def _sample_shed(**overrides) -> ShedResult:
    base = ShedResult(
        tier="pool",
        entity="switch.pool",
        desired_on=False,
        applied=False,
        verified=False,
        skipped_reason=SKIP_SHADOW_MODE,
    )
    for key, value in overrides.items():
        setattr(base, key, value)
    return base


def test_executions_audit_equal_none_prev() -> None:
    assert executions_audit_equal(None, _sample_execution()) is False


def test_executions_audit_equal_same_except_ts() -> None:
    a = _sample_execution(ts=utcnow())
    b = _sample_execution(ts=utcnow() + timedelta(seconds=30))
    assert executions_audit_equal(a, b) is True


@pytest.mark.parametrize(
    ("mutator",),
    [
        (lambda e: setattr(e, "requested", 40.0),),
        (lambda e: setattr(e, "applied", True),),
        (lambda e: setattr(e, "verified", True),),
        (lambda e: setattr(e, "skipped_reason", None),),
        (lambda e: setattr(e, "error", "write failed"),),
        (lambda e: setattr(e, "capability", Capability.GRID_CHARGE_ENABLE),),
    ],
)
def test_executions_audit_equal_detects_change(mutator) -> None:
    a = _sample_execution()
    b = _sample_execution()
    mutator(b)
    assert executions_audit_equal(a, b) is False


def test_shed_executions_audit_equal_none_prev() -> None:
    assert shed_executions_audit_equal(None, _sample_shed()) is False


def test_shed_executions_audit_equal_same_except_ts() -> None:
    a = _sample_shed(ts=utcnow())
    b = _sample_shed(ts=utcnow() + timedelta(seconds=30))
    assert shed_executions_audit_equal(a, b) is True


@pytest.mark.parametrize(
    ("mutator",),
    [
        (lambda r: setattr(r, "desired_on", True),),
        (lambda r: setattr(r, "applied", True),),
        (lambda r: setattr(r, "verified", True),),
        (lambda r: setattr(r, "skipped_reason", None),),
        (lambda r: setattr(r, "error", "toggle failed"),),
        (lambda r: setattr(r, "entity", "switch.ac"),),
        (lambda r: setattr(r, "companions_restored", ["switch.light"]),),
    ],
)
def test_shed_executions_audit_equal_detects_change(mutator) -> None:
    a = _sample_shed()
    b = _sample_shed()
    mutator(b)
    assert shed_executions_audit_equal(a, b) is False


@pytest.mark.asyncio
async def test_executor_skips_duplicate_execution_save(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = MagicMock()
    adapter.supports = MagicMock(return_value=True)
    ha = MagicMock()
    ha.is_stale = MagicMock(return_value=False)
    adapter.read_capability = AsyncMock(return_value=32.0)
    ex = Executor(adapter, ha, BatteryConfig(), ControlConfig())

    save_mock = AsyncMock()
    monkeypatch.setattr("app.control.executor.repo.save_execution", save_mock)

    res = _sample_execution()
    await ex._maybe_save_execution(res)
    await ex._maybe_save_execution(_sample_execution(ts=utcnow() + timedelta(seconds=5)))

    save_mock.assert_called_once()


@pytest.mark.asyncio
async def test_executor_saves_when_execution_changes(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = MagicMock()
    ha = MagicMock()
    ex = Executor(adapter, ha, BatteryConfig(), ControlConfig())

    save_mock = AsyncMock()
    monkeypatch.setattr("app.control.executor.repo.save_execution", save_mock)

    await ex._maybe_save_execution(_sample_execution())
    await ex._maybe_save_execution(_sample_execution(requested=40.0))

    assert save_mock.call_count == 2
