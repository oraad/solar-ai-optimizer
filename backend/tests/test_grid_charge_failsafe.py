"""Executor grid-charge-at-max fail-safe tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.adapters.base import InverterAdapter
from app.config import BatteryConfig, ControlConfig
from app.control.executor import Executor
from app.ha.client import HAClient
from app.models import Capability, Telemetry, utcnow


class _StubAdapter(InverterAdapter):
    def __init__(self) -> None:
        self.applied: list[tuple[Capability, float | bool]] = []

    async def read_telemetry(self) -> Telemetry:
        return Telemetry(ts=utcnow())

    def supports(self, capability: Capability) -> bool:
        return capability in (
            Capability.GRID_CHARGE_ENABLE,
            Capability.MAX_GRID_CHARGE_CURRENT,
        )

    async def read_capability(self, capability: Capability):
        return None

    async def set_grid_charge(self, enabled: bool) -> None:
        self.applied.append((Capability.GRID_CHARGE_ENABLE, enabled))

    async def set_max_grid_charge_current(self, amps: float) -> None:
        self.applied.append((Capability.MAX_GRID_CHARGE_CURRENT, amps))


@pytest.fixture
def executor(monkeypatch: pytest.MonkeyPatch) -> tuple[Executor, _StubAdapter]:
    monkeypatch.setattr("app.storage.repo.save_execution", AsyncMock())
    adapter = _StubAdapter()
    ha = MagicMock(spec=HAClient)
    ha.is_stale = MagicMock(return_value=False)
    battery = BatteryConfig(max_grid_charge_a=72.0)
    control = ControlConfig()
    ex = Executor(adapter, ha, battery, control)
    ex._verify = AsyncMock(return_value=True)  # noqa: SLF001
    return ex, adapter


@pytest.mark.asyncio
async def test_apply_grid_charge_at_max_enables_grid_and_sets_current(executor):
    ex, adapter = executor
    results = await ex.apply_grid_charge_at_max()
    assert len(results) == 2
    assert all(r.applied for r in results)
    caps = [c for c, _ in adapter.applied]
    assert Capability.GRID_CHARGE_ENABLE in caps
    assert Capability.MAX_GRID_CHARGE_CURRENT in caps
    current = dict(adapter.applied)
    assert current[Capability.GRID_CHARGE_ENABLE] is True
    assert current[Capability.MAX_GRID_CHARGE_CURRENT] == 72.0


@pytest.mark.asyncio
async def test_kill_switch_delegates_to_grid_charge_at_max(executor):
    ex, adapter = executor
    await ex.kill_switch()
    assert adapter.applied
    assert adapter.applied[0] == (Capability.GRID_CHARGE_ENABLE, True)
