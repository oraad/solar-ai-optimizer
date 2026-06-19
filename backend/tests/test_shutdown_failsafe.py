"""Graceful shutdown applies grid-charge-at-max fail-safe."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
async def test_shutdown_applies_failsafe_before_aclose(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 't.db'}")
    from app.config import get_settings
    from app.config_store import ConfigStore
    from app.orchestrator import Orchestrator

    settings = get_settings()
    cfg_yaml = """
battery:
  capacity_kwh: 10
  max_grid_charge_a: 55
fail_safe:
  shutdown_failsafe_enabled: true
inverter:
  write:
    grid_charge_enable: switch.grid_charge
    max_grid_charge_current: number.max_grid_charge_current
"""
    (tmp_path / "base.yaml").write_text(cfg_yaml, encoding="utf-8")
    store = ConfigStore(str(tmp_path / "base.yaml"), str(tmp_path / "runtime.yaml"))
    orch = Orchestrator(settings, store)

    orch.executor = MagicMock()
    orch.executor.apply_grid_charge_at_max = AsyncMock(return_value=[])
    orch.ha.aclose = AsyncMock()
    orch._stream_task = None

    await orch.shutdown()

    orch.executor.apply_grid_charge_at_max.assert_awaited_once()
    orch.ha.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_shutdown_skips_failsafe_when_disabled(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 't.db'}")
    from app.config import get_settings
    from app.config_store import ConfigStore
    from app.orchestrator import Orchestrator

    settings = get_settings()
    cfg_yaml = """
fail_safe:
  shutdown_failsafe_enabled: false
inverter:
  write:
    grid_charge_enable: switch.grid_charge
"""
    (tmp_path / "base.yaml").write_text(cfg_yaml, encoding="utf-8")
    store = ConfigStore(str(tmp_path / "base.yaml"), str(tmp_path / "runtime.yaml"))
    orch = Orchestrator(settings, store)

    orch.executor = MagicMock()
    orch.executor.apply_grid_charge_at_max = AsyncMock(return_value=[])
    orch.ha.aclose = AsyncMock()
    orch._stream_task = None

    await orch.shutdown()

    orch.executor.apply_grid_charge_at_max.assert_not_called()
