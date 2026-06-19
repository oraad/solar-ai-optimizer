"""clear_overrides unpause behavior."""

from __future__ import annotations

import pytest

from app.models import Override
from app.orchestrator import Orchestrator


def test_clear_overrides_unpauses(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 't.db'}")
    from app.config import get_settings
    from app.config_store import ConfigStore

    settings = get_settings()
    (tmp_path / "base.yaml").write_text("battery:\n  capacity_kwh: 10\n")
    store = ConfigStore(str(tmp_path / "base.yaml"), str(tmp_path / "runtime.yaml"))
    orch = Orchestrator(settings, store)
    orch.paused = True
    orch.override = Override(reserve_soc=55.0)
    result = orch.clear_overrides()
    assert result["cleared"] is True
    assert orch.paused is False
    assert orch.override.reserve_soc is None
