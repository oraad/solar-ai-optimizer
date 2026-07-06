"""Independent shedding, grid charge, and optimization subsystems."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.config import AppConfig, EngineConfig, GridChargeConfig, LoadSheddingConfig
from app.models import BlackoutRisk, Capability, ControlAction, Decision, Override, ReserveTarget, ShedAction, utcnow
from app.subsystems import deployment_profile, plan_grid_charge, plan_optimization
from tests.conftest import DUMMY_MSG


def _base_cfg(**patch) -> AppConfig:
    cfg = AppConfig()
    if patch:
        data = cfg.model_dump()
        for key, val in patch.items():
            if isinstance(val, dict) and key in data and isinstance(data[key], dict):
                data[key] = {**data[key], **val}
            else:
                data[key] = val
        cfg = AppConfig.model_validate(data)
    return cfg


def test_deployment_profile_shed_primary():
    cfg = _base_cfg(
        load_shedding={"enabled": True},
        grid_charge={"enabled": False},
        engine={"enabled": False},
    )
    assert deployment_profile(cfg) == "shed_primary"


def test_deployment_profile_shed_advisory():
    cfg = _base_cfg(
        load_shedding={"enabled": True},
        grid_charge={"enabled": False},
        engine={"enabled": True},
    )
    assert deployment_profile(cfg) == "shed_advisory"


def test_plan_grid_charge_requires_engine():
    cfg = _base_cfg(grid_charge={"enabled": True}, engine={"enabled": False})
    assert plan_grid_charge(cfg) is False
    cfg = _base_cfg(grid_charge={"enabled": True}, engine={"enabled": True})
    assert plan_grid_charge(cfg) is True


def test_plan_optimization():
    cfg = _base_cfg(engine={"enabled": False})
    assert plan_optimization(cfg) is False


def _decision_with_both() -> Decision:
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
    )


@pytest.mark.asyncio
async def test_pause_grid_charge_only_still_applies_shed(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 't.db'}")
    from app.config import get_settings
    from app.config_store import ConfigStore
    from app.orchestrator import Orchestrator

    settings = get_settings()
    (tmp_path / "base.yaml").write_text(
        "battery:\n  capacity_kwh: 10\n"
        "load_shedding:\n  enabled: true\n  tiers:\n    - name: pool\n"
        "      switches: [switch.pool]\n      shed_below_soc: 40\n"
        "      restore_above_soc: 55\n      priority: 1\n"
    )
    store = ConfigStore(str(tmp_path / "base.yaml"), str(tmp_path / "runtime.yaml"))
    orch = Orchestrator(settings, store)
    orch.cfg.load_shedding.enabled = True

    orch.paused_grid_charge = True
    orch.paused_shedding = False
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
    orch._decide = MagicMock(return_value=_decision_with_both())
    orch._broadcast = AsyncMock()

    monkeypatch.setattr("app.orchestrator.repo.save_decision", AsyncMock())

    await orch.control_cycle()

    orch.executor.apply_decision.assert_not_called()
    orch.executor.apply_shed_actions.assert_called_once()


@pytest.mark.asyncio
async def test_grid_charge_disabled_skips_apply_decision(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 't.db'}")
    from app.config import get_settings
    from app.config_store import ConfigStore
    from app.orchestrator import Orchestrator

    settings = get_settings()
    (tmp_path / "base.yaml").write_text("battery:\n  capacity_kwh: 10\n")
    store = ConfigStore(str(tmp_path / "base.yaml"), str(tmp_path / "runtime.yaml"))
    orch = Orchestrator(settings, store)
    orch.cfg.grid_charge.enabled = False

    orch.collector = MagicMock()
    orch.collector.sample = AsyncMock(
        return_value=MagicMock(grid_present=True, battery_soc=60.0, ts=utcnow())
    )
    orch.executor = MagicMock()
    orch.executor.apply_decision = AsyncMock(return_value=[])
    orch.executor.apply_shed_actions = AsyncMock(return_value=[])
    orch.forecast = MagicMock()
    orch.forecast.current = None
    orch.reactive = MagicMock()
    orch.reactive.compute_stats = AsyncMock(return_value=MagicMock())
    orch._decide = MagicMock(return_value=_decision_with_both())
    orch._broadcast = AsyncMock()

    monkeypatch.setattr("app.orchestrator.repo.save_decision", AsyncMock())

    await orch.control_cycle()

    orch.executor.apply_decision.assert_not_called()


@pytest.mark.asyncio
async def test_pause_engine_skips_both(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 't.db'}")
    from app.config import get_settings
    from app.config_store import ConfigStore
    from app.orchestrator import Orchestrator

    settings = get_settings()
    (tmp_path / "base.yaml").write_text("battery:\n  capacity_kwh: 10\n")
    store = ConfigStore(str(tmp_path / "base.yaml"), str(tmp_path / "runtime.yaml"))
    orch = Orchestrator(settings, store)

    orch.paused_shedding = True
    orch.paused_grid_charge = True
    orch.paused_optimization = True
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
    orch._decide = MagicMock(return_value=_decision_with_both())
    orch._broadcast = AsyncMock()

    monkeypatch.setattr("app.orchestrator.repo.save_decision", AsyncMock())

    await orch.control_cycle()

    orch.executor.apply_decision.assert_not_called()
    orch.executor.apply_shed_actions.assert_not_called()


@pytest.mark.asyncio
async def test_legacy_paused_runtime_migration(monkeypatch: pytest.MonkeyPatch, tmp_path):
    from app.runtime_state import save

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 't.db'}")
    save(str(tmp_path), {"paused": True})

    from app.config import get_settings
    from app.config_store import ConfigStore
    from app.orchestrator import Orchestrator

    get_settings.cache_clear()
    settings = get_settings()
    (tmp_path / "base.yaml").write_text("battery:\n  capacity_kwh: 10\n")
    store = ConfigStore(str(tmp_path / "base.yaml"), str(tmp_path / "runtime.yaml"))
    orch = Orchestrator(settings, store)

    orch.collector = MagicMock()
    orch.collector.prime = AsyncMock()
    orch.collector.run_stream_safe = AsyncMock()
    orch.forecast = MagicMock()
    orch.forecast.refresh = AsyncMock(return_value=None)
    orch.forecast.load_model = MagicMock(return_value=False)
    orch.ha = MagicMock()
    orch.ha.ping = AsyncMock(return_value=False)
    orch.reactive.compute_stats = AsyncMock(return_value=None)
    monkeypatch.setattr("app.orchestrator.init_db", AsyncMock())
    monkeypatch.setattr(
        "app.orchestrator.asyncio.create_task",
        lambda coro: asyncio.ensure_future(coro),
    )

    await orch.setup()

    assert orch.paused_shedding is True
    assert orch.paused_grid_charge is True
    assert orch.paused_optimization is True


def _orch_for_override_tests(monkeypatch: pytest.MonkeyPatch, tmp_path) -> object:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 't.db'}")
    from app.config import get_settings
    from app.config_store import ConfigStore
    from app.orchestrator import Orchestrator

    settings = get_settings()
    (tmp_path / "base.yaml").write_text("battery:\n  capacity_kwh: 10\n")
    store = ConfigStore(str(tmp_path / "base.yaml"), str(tmp_path / "runtime.yaml"))
    orch = Orchestrator(settings, store)
    orch.cfg.grid_charge.enabled = True
    orch.cfg.engine.enabled = True
    orch.collector = MagicMock()
    orch.collector.sample = AsyncMock(
        return_value=MagicMock(grid_present=True, battery_soc=60.0, ts=utcnow())
    )
    orch.executor = MagicMock()
    orch.executor.apply_decision = AsyncMock(return_value=[])
    orch.executor.apply_shed_actions = AsyncMock(return_value=[])
    orch.forecast = MagicMock()
    orch.forecast.current = None
    orch.reactive = MagicMock()
    orch.reactive.compute_stats = AsyncMock(return_value=MagicMock())
    orch._decide = MagicMock(return_value=_decision_with_both())
    orch._broadcast = AsyncMock()
    monkeypatch.setattr("app.orchestrator.repo.save_decision", AsyncMock())
    return orch


def _decision_with_grid_actions() -> Decision:
    return Decision(
        ts=utcnow(),
        reserve=ReserveTarget(
            target_soc=50,
            solar_bridge_soc=55,
            autonomy_floor_soc=30,
            rationale=DUMMY_MSG,
        ),
        actions=[
            ControlAction(
                capability=Capability.GRID_CHARGE_ENABLE,
                value=True,
                reason=DUMMY_MSG,
                priority=120,
            ),
        ],
        shed_actions=[],
        blackout_risk=BlackoutRisk.LOW,
        blackout_risk_score=0.1,
        summary=DUMMY_MSG,
    )


@pytest.mark.asyncio
async def test_force_grid_charge_while_paused_applies_decision(
    monkeypatch: pytest.MonkeyPatch, tmp_path
):
    orch = _orch_for_override_tests(monkeypatch, tmp_path)
    orch.paused_grid_charge = True
    orch.override.force_grid_charge = True
    orch._decide = MagicMock(return_value=_decision_with_grid_actions())

    await orch.control_cycle()

    orch.executor.apply_decision.assert_called_once()


@pytest.mark.asyncio
async def test_apply_override_force_on_pauses_grid(monkeypatch: pytest.MonkeyPatch, tmp_path):
    orch = _orch_for_override_tests(monkeypatch, tmp_path)

    await orch.apply_override(Override(force_grid_charge=True))

    assert orch.override.force_grid_charge is True
    assert orch.paused_grid_charge is True


@pytest.mark.asyncio
async def test_apply_override_resume_grid_clears_force(
    monkeypatch: pytest.MonkeyPatch, tmp_path
):
    orch = _orch_for_override_tests(monkeypatch, tmp_path)
    orch.override.force_grid_charge = True
    orch.paused_grid_charge = True

    await orch.apply_override(Override(pause_grid_charge=False))

    assert orch.override.force_grid_charge is None
    assert orch.paused_grid_charge is False


@pytest.mark.asyncio
async def test_apply_override_resume_all_clears_force(
    monkeypatch: pytest.MonkeyPatch, tmp_path
):
    orch = _orch_for_override_tests(monkeypatch, tmp_path)
    orch.override.force_grid_charge = True
    orch.paused_grid_charge = True
    orch.paused_shedding = True
    orch.paused_optimization = True

    await orch.apply_override(Override(pause_engine=False))

    assert orch.override.force_grid_charge is None
    assert orch.paused_grid_charge is False
