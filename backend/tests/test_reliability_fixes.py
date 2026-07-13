"""Tests for Phase 1 reliability fixes.

Covers:
- Atomic runtime_state writes (temp file + os.replace + chmod 0o600)
- Atomic shed_snapshot writes
- SQLite WAL pragma applied in init_db
- Shutdown shed restore on graceful shutdown
- /metrics Bearer token auth (METRICS_TOKEN / api_token)
- /metrics process_start_time_seconds gauge
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.auth import AuthGateMiddleware, UserContextMiddleware
from app.api.metrics import metrics_router
from app.models import SystemStatus, utcnow


# ---------------------------------------------------------------------------
# 1. Atomic runtime_state writes
# ---------------------------------------------------------------------------


def test_runtime_state_save_is_atomic(tmp_path: Path) -> None:
    """save() must write to a .tmp file then rename — no partial writes."""
    from app import runtime_state

    writes: list[str] = []
    originals_replace = Path.replace

    def _spy_replace(self: Path, target: Path) -> None:  # type: ignore[override]
        writes.append(self.name)
        return originals_replace(self, target)

    with patch.object(Path, "replace", _spy_replace):
        runtime_state.save(str(tmp_path), {"paused_shedding": True})

    assert any(n.endswith(".tmp") for n in writes), (
        "Expected an intermediate .tmp rename; got: %s" % writes
    )
    saved = json.loads((tmp_path / "runtime_state.json").read_text(encoding="utf-8"))
    assert saved["paused_shedding"] is True


def test_runtime_state_save_creates_parent(tmp_path: Path) -> None:
    from app import runtime_state

    nested = str(tmp_path / "sub" / "dir")
    runtime_state.save(nested, {"x": 1})
    assert (Path(nested) / "runtime_state.json").exists()


def test_runtime_state_load_missing(tmp_path: Path) -> None:
    from app import runtime_state

    assert runtime_state.load(str(tmp_path)) == {}


def test_runtime_state_load_corrupt(tmp_path: Path) -> None:
    from app import runtime_state

    (tmp_path / "runtime_state.json").write_text("INVALID", encoding="utf-8")
    result = runtime_state.load(str(tmp_path))
    assert result == {}


# ---------------------------------------------------------------------------
# 2. Atomic shed_snapshot writes
# ---------------------------------------------------------------------------


def test_shed_snapshots_save_is_atomic(tmp_path: Path) -> None:
    from app.shed_snapshots import ShedSnapshotStore

    store = ShedSnapshotStore(str(tmp_path))
    renames: list[str] = []
    originals_replace = Path.replace

    def _spy_replace(self: Path, target: Path) -> None:  # type: ignore[override]
        renames.append(self.name)
        return originals_replace(self, target)

    with patch.object(Path, "replace", _spy_replace):
        store.capture("switch.pool", was_on=True)

    assert any(n.endswith(".tmp") for n in renames), (
        "Expected .tmp rename for shed_snapshots; got: %s" % renames
    )
    snap = store.get("switch.pool")
    assert snap is not None and snap.was_on is True


# ---------------------------------------------------------------------------
# 3. SQLite WAL pragma
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_init_db_applies_wal_pragma(tmp_path: Path) -> None:
    """init_db must set journal_mode=WAL and busy_timeout on SQLite connections."""
    import importlib

    import app.storage.db as db_module

    db_module._engine = None
    db_module._sessionmaker = None

    db_url = f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"
    executed: list[str] = []

    _orig_init = db_module.init_db

    async def _patched_init(database_url: str) -> None:
        from sqlalchemy.ext.asyncio import create_async_engine

        engine = create_async_engine(database_url, future=True, echo=False)
        async with engine.begin() as conn:
            result = await conn.exec_driver_sql("PRAGMA journal_mode")
            row = result.fetchone()
            if row:
                executed.append(f"journal_mode={row[0]}")
        await engine.dispose()

    # Run the real init_db then inspect the file via a fresh connection.
    await db_module.init_db(db_url)

    # Verify WAL was applied by checking the db file's header or querying.
    from sqlalchemy.ext.asyncio import create_async_engine

    engine2 = create_async_engine(db_url, future=True, echo=False)
    async with engine2.begin() as conn:
        result = await conn.exec_driver_sql("PRAGMA journal_mode")
        row = result.fetchone()
        assert row is not None
        assert row[0] == "wal", f"Expected WAL, got: {row[0]}"
    await engine2.dispose()
    await db_module.close_db()


# ---------------------------------------------------------------------------
# 4. Shutdown shed restore
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_shutdown_restores_sheds_when_snapshots_exist(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """When shed snapshots are present shutdown must call restore_all_sheds."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 't.db'}")
    from app.config import get_settings
    get_settings.cache_clear()
    from app.config_store import ConfigStore
    from app.orchestrator import Orchestrator
    from app.shed_snapshots import ShedSnapshotStore

    settings = get_settings()
    cfg_yaml = """
battery:
  capacity_kwh: 10
load_shedding:
  enabled: true
  tiers:
    - name: tier1
      entities:
        - switch.pool
fail_safe:
  shutdown_failsafe_enabled: false
"""
    (tmp_path / "base.yaml").write_text(cfg_yaml, encoding="utf-8")
    store = ConfigStore(str(tmp_path / "base.yaml"), str(tmp_path / "runtime.yaml"))
    orch = Orchestrator(settings, store)

    # Inject a snapshot so shed_restore_needed is True.
    orch.snapshot_store.capture("switch.pool", was_on=True)

    orch.executor = MagicMock()
    orch.executor.restore_all_sheds = AsyncMock(return_value=[])
    orch.executor.apply_grid_charge_at_max = AsyncMock(return_value=[])
    orch.ha.aclose = AsyncMock()
    orch._stream_task = None

    await orch.shutdown()

    orch.executor.restore_all_sheds.assert_awaited_once()
    orch.executor.apply_grid_charge_at_max.assert_not_called()


@pytest.mark.asyncio
async def test_shutdown_restores_sheds_then_grid_failsafe(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """With both snapshots and grid fail-safe, sheds are restored before grid charge."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 't.db'}")
    from app.config import get_settings
    get_settings.cache_clear()
    from app.config_store import ConfigStore
    from app.orchestrator import Orchestrator

    settings = get_settings()
    cfg_yaml = """
battery:
  capacity_kwh: 10
grid_charge:
  max_grid_charge_a: 55
load_shedding:
  enabled: true
  tiers:
    - name: tier1
      entities:
        - switch.pool
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
    orch.snapshot_store.capture("switch.pool", was_on=True)

    call_order: list[str] = []

    async def _restore(*_a, **_kw):
        call_order.append("restore")
        return []

    async def _grid_max(*_a, **_kw):
        call_order.append("grid_max")
        return []

    orch.executor = MagicMock()
    orch.executor.restore_all_sheds = AsyncMock(side_effect=_restore)
    orch.executor.apply_grid_charge_at_max = AsyncMock(side_effect=_grid_max)
    orch.ha.aclose = AsyncMock()
    orch._stream_task = None

    await orch.shutdown()

    assert call_order == ["restore", "grid_max"], (
        "Expected restore before grid_max; got: %s" % call_order
    )


@pytest.mark.asyncio
async def test_shutdown_no_sheds_no_snapshots_skips_restore(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """With no snapshots and shedding disabled, restore_all_sheds is not called."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 't.db'}")
    from app.config import get_settings
    get_settings.cache_clear()
    from app.config_store import ConfigStore
    from app.orchestrator import Orchestrator

    settings = get_settings()
    cfg_yaml = """
fail_safe:
  shutdown_failsafe_enabled: false
"""
    (tmp_path / "base.yaml").write_text(cfg_yaml, encoding="utf-8")
    store = ConfigStore(str(tmp_path / "base.yaml"), str(tmp_path / "runtime.yaml"))
    orch = Orchestrator(settings, store)

    orch.executor = MagicMock()
    orch.executor.restore_all_sheds = AsyncMock(return_value=[])
    orch.executor.apply_grid_charge_at_max = AsyncMock(return_value=[])
    orch.ha.aclose = AsyncMock()
    orch._stream_task = None

    await orch.shutdown()

    orch.executor.restore_all_sheds.assert_not_called()
    orch.executor.apply_grid_charge_at_max.assert_not_called()


# ---------------------------------------------------------------------------
# 5. /metrics Bearer token auth + process_start_time_seconds
# ---------------------------------------------------------------------------


def _metrics_client(monkeypatch, **env_overrides) -> TestClient:
    from app.config import get_settings

    monkeypatch.delenv("METRICS_TOKEN", raising=False)
    monkeypatch.delenv("API_TOKEN", raising=False)
    get_settings.cache_clear()
    for k, v in env_overrides.items():
        monkeypatch.setenv(k, v)
    orch = MagicMock()
    orch.build_status.return_value = SystemStatus(
        ha_connected=True, telemetry_stale=False, last_updated=utcnow()
    )
    app = FastAPI()
    app.state.orchestrator = orch
    app.state.admin_resolver = AsyncMock()
    app.add_middleware(AuthGateMiddleware)
    app.add_middleware(UserContextMiddleware)
    app.include_router(metrics_router)
    return TestClient(app)


def test_metrics_bearer_api_token(monkeypatch) -> None:
    """Bearer api_token grants access to /metrics."""
    monkeypatch.delenv("METRICS_TOKEN", raising=False)
    client = _metrics_client(monkeypatch, API_TOKEN="secret-api")
    res = client.get("/metrics", headers={"Authorization": "Bearer secret-api"})
    assert res.status_code == 200
    assert "solar_control_cycles_total" in res.text


def test_metrics_bearer_metrics_token(monkeypatch) -> None:
    """Dedicated METRICS_TOKEN grants access without api_token."""
    monkeypatch.delenv("API_TOKEN", raising=False)
    client = _metrics_client(monkeypatch, METRICS_TOKEN="scrape-token")
    res = client.get("/metrics", headers={"Authorization": "Bearer scrape-token"})
    assert res.status_code == 200
    assert "solar_control_cycles_total" in res.text


def test_metrics_wrong_bearer_rejected(monkeypatch) -> None:
    """Wrong Bearer token is rejected with 401."""
    monkeypatch.delenv("METRICS_TOKEN", raising=False)
    client = _metrics_client(monkeypatch, API_TOKEN="correct")
    res = client.get("/metrics", headers={"Authorization": "Bearer wrong"})
    assert res.status_code == 401


def test_metrics_no_auth_open_dev(monkeypatch) -> None:
    """When no credentials are configured the endpoint is open (dev mode)."""
    monkeypatch.delenv("API_TOKEN", raising=False)
    monkeypatch.delenv("METRICS_TOKEN", raising=False)
    monkeypatch.delenv("LOCAL_ADMIN_PASSWORD", raising=False)
    monkeypatch.delenv("LOCAL_ADMIN_PASSWORD_HASH", raising=False)
    monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)
    client = _metrics_client(monkeypatch)
    res = client.get("/metrics")
    assert res.status_code == 200


def test_metrics_process_start_time_present(monkeypatch) -> None:
    """process_start_time_seconds gauge must appear in Prometheus output."""
    monkeypatch.delenv("API_TOKEN", raising=False)
    monkeypatch.delenv("METRICS_TOKEN", raising=False)
    monkeypatch.delenv("LOCAL_ADMIN_PASSWORD", raising=False)
    monkeypatch.delenv("LOCAL_ADMIN_PASSWORD_HASH", raising=False)
    monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)
    client = _metrics_client(monkeypatch)
    res = client.get("/metrics")
    assert res.status_code == 200
    assert "process_start_time_seconds" in res.text
