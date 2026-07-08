"""simulate_decision dry-run must not mutate metrics or persist."""

from __future__ import annotations

import pytest

from app.models import Telemetry, utcnow
from app.observability.metrics import metrics
from app.orchestrator import Orchestrator


@pytest.mark.asyncio
async def test_simulate_decision_no_metrics_mutation(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'sim.db'}")
    from app.config import get_settings
    from app.config_store import ConfigStore

    settings = get_settings()
    (tmp_path / "base.yaml").write_text(
        "battery:\n  capacity_kwh: 10\n"
        "engine:\n  enabled: true\n"
    )
    store = ConfigStore(str(tmp_path / "base.yaml"), str(tmp_path / "runtime.yaml"))
    orch = Orchestrator(settings, store)
    await orch.setup()

    orch.collector.set_latest(
        Telemetry(
            battery_soc=50.0,
            load_power=400.0,
            pv_power=800.0,
            grid_present=True,
            ts=utcnow(),
        )
    )

    before_cycles = metrics.control_cycles
    before_mpc = metrics.mpc_fallbacks

    result = orch.simulate_decision()
    assert result is not None

    assert metrics.control_cycles == before_cycles
    assert metrics.mpc_fallbacks == before_mpc
    assert orch.latest_decision is None

    await orch.shutdown()


@pytest.mark.asyncio
async def test_simulate_decision_none_without_telemetry(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'sim2.db'}")
    monkeypatch.setenv("DEMO_MODE", "false")
    from app.config import get_settings
    from app.config_store import ConfigStore

    settings = get_settings()
    (tmp_path / "base.yaml").write_text("battery:\n  capacity_kwh: 10\n")
    store = ConfigStore(str(tmp_path / "base.yaml"), str(tmp_path / "runtime.yaml"))
    orch = Orchestrator(settings, store)
    await orch.setup()
    orch.collector.set_latest(None)
    assert orch.simulate_decision() is None
    await orch.shutdown()
