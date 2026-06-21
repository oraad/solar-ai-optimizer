"""Grid stats are populated at startup and survive compute failures."""

from __future__ import annotations

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models import GridStats, Telemetry, utcnow


@pytest.mark.asyncio
async def test_setup_populates_grid_stats(
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

    sample_telemetry = Telemetry(
        ts=utcnow(),
        battery_soc=50.0,
        grid_present=True,
    )
    orch.collector.sample = AsyncMock(return_value=sample_telemetry)
    orch.collector.prime = AsyncMock()
    orch.ha.ping = AsyncMock(return_value=True)
    orch.forecast.refresh = AsyncMock()
    orch.forecast.load_model = MagicMock(return_value=False)
    orch.reactive.compute_stats = AsyncMock(
        return_value=GridStats(avg_window_minutes=30.0, currently_present=True)
    )

    monkeypatch.setattr(
        "app.orchestrator.asyncio.create_task",
        lambda coro: asyncio.ensure_future(coro),
    )

    await orch.setup()

    assert orch.latest_grid_stats is not None
    assert isinstance(orch.latest_grid_stats, GridStats)
    assert orch.latest_grid_stats.currently_present is True


@pytest.mark.asyncio
async def test_control_cycle_survives_grid_stats_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 't.db'}")
    from app.config import get_settings
    from app.config_store import ConfigStore
    from app.models import Decision, ReserveTarget
    from app.orchestrator import Orchestrator

    settings = get_settings()
    (tmp_path / "base.yaml").write_text("battery:\n  capacity_kwh: 10\n")
    store = ConfigStore(str(tmp_path / "base.yaml"), str(tmp_path / "runtime.yaml"))
    orch = Orchestrator(settings, store)

    orch.collector.sample = AsyncMock(
        return_value=Telemetry(
            ts=utcnow(),
            battery_soc=50.0,
            grid_present=False,
        )
    )
    orch.reactive.compute_stats = AsyncMock(side_effect=RuntimeError("db down"))
    orch._decide = MagicMock(
        return_value=Decision(
            ts=utcnow(),
            reserve=ReserveTarget(
                target_soc=50,
                solar_bridge_soc=55,
                autonomy_floor_soc=30,
                rationale="test",
            ),
            summary="ok",
            shadow_mode=True,
        )
    )
    orch.executor.apply_decision = AsyncMock(return_value=[])
    orch.forecast = MagicMock()
    orch.forecast.current = None
    orch._broadcast = AsyncMock()
    monkeypatch.setattr("app.orchestrator.repo.save_decision", AsyncMock())

    with caplog.at_level(logging.WARNING):
        decision = await orch.control_cycle()

    assert decision is not None
    assert orch.latest_grid_stats is None
    assert any("grid stats failed" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_grid_stats_failure_clears_prior_snapshot(
    monkeypatch: pytest.MonkeyPatch, tmp_path, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 't.db'}")
    from app.config import get_settings
    from app.config_store import ConfigStore
    from app.models import Decision, ReserveTarget
    from app.orchestrator import Orchestrator

    settings = get_settings()
    (tmp_path / "base.yaml").write_text("battery:\n  capacity_kwh: 10\n")
    store = ConfigStore(str(tmp_path / "base.yaml"), str(tmp_path / "runtime.yaml"))
    orch = Orchestrator(settings, store)

    orch.latest_grid_stats = GridStats(avg_window_minutes=45.0, currently_present=True)
    orch.collector.sample = AsyncMock(
        return_value=Telemetry(ts=utcnow(), battery_soc=50.0, grid_present=True)
    )
    orch.reactive.compute_stats = AsyncMock(side_effect=RuntimeError("db down"))
    orch._decide = MagicMock(
        return_value=Decision(
            ts=utcnow(),
            reserve=ReserveTarget(
                target_soc=50,
                solar_bridge_soc=55,
                autonomy_floor_soc=30,
                rationale="test",
            ),
            summary="ok",
            shadow_mode=True,
        )
    )
    orch.executor.apply_decision = AsyncMock(return_value=[])
    orch.forecast = MagicMock()
    orch.forecast.current = None
    orch._broadcast = AsyncMock()
    monkeypatch.setattr("app.orchestrator.repo.save_decision", AsyncMock())

    with caplog.at_level(logging.WARNING):
        await orch.control_cycle()

    assert orch.latest_grid_stats is None
