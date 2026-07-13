"""Locale middleware and API localization."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.auth import AuthGateMiddleware, UserContextMiddleware
from app.api.routes import router
from app.i18n import msg
from app.i18n.middleware import LocaleMiddleware
from app.i18n.serialize import localize_payload
from app.models import Decision, ReserveTarget, SystemStatus, utcnow
from tests.conftest import wire_orchestrator_site_tz


def _orch_with_decision(decision: Decision | None = None) -> MagicMock:
    orch = MagicMock()
    orch.build_status.return_value = SystemStatus(
        ha_connected=True,
        telemetry_stale=False,
        telemetry_age_seconds=1.0,
        forecast_misconfigured=False,
        forecast_degraded=False,
        engine_mode="rules",
        engine_active="rules",
        shadow_mode=True,
        paused=False,
        last_updated=utcnow(),
    )
    orch.latest_decision = decision
    orch.forecast.current = None
    wire_orchestrator_site_tz(orch)
    orch.ha.is_reachable.return_value = True
    orch.shadow_mode = True
    orch.paused = False
    orch.cfg.fail_safe = MagicMock(shutdown_failsafe_enabled=True)
    orch.heartbeat.last_pulse_at = None
    return orch


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("API_TOKEN", raising=False)
    monkeypatch.delenv("LOCAL_ADMIN_PASSWORD", raising=False)
    monkeypatch.delenv("LOCAL_ADMIN_PASSWORD_HASH", raising=False)
    from app.config import get_settings

    get_settings.cache_clear()

    decision = Decision(
        reserve=ReserveTarget(
            target_soc=50,
            solar_bridge_soc=45,
            autonomy_floor_soc=40,
            rationale=msg("engine.grid.absent"),
        ),
        summary=msg(
            "engine.summary.with_priorities_absent",
            order="resilience,savings,self_sufficiency",
            soc="50",
            target=50,
            risk="low",
            extra="",
            advisory_suffix="",
            advisory_kw=0,
        ),
    )
    orch = _orch_with_decision(decision)
    app = FastAPI()
    app.state.orchestrator = orch
    app.state.admin_resolver = AsyncMock()
    app.add_middleware(AuthGateMiddleware)
    app.add_middleware(LocaleMiddleware)
    app.add_middleware(UserContextMiddleware)
    app.include_router(router)
    return TestClient(app)


def test_status_respects_locale_header(client):
    res_en = client.get("/api/plan", headers={"X-Solar-Locale": "en"})
    assert res_en.status_code == 200
    rationale_en = res_en.json()["decision"]["reserve"]["rationale"]
    assert "Grid absent" in rationale_en

    res_fr = client.get("/api/plan", headers={"X-Solar-Locale": "fr"})
    assert res_fr.status_code == 200
    rationale_fr = res_fr.json()["decision"]["reserve"]["rationale"]
    assert "Réseau absent" in rationale_fr


@pytest.fixture
def authed_client(monkeypatch):
    orch = _orch_with_decision()
    monkeypatch.setenv("API_TOKEN", "secret-token")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("HA_TOKEN", "")
    monkeypatch.setenv("HA_BASE_URL", "http://127.0.0.1:9")
    from app.config import get_settings

    get_settings.cache_clear()

    app = FastAPI()
    app.state.orchestrator = orch
    app.state.admin_resolver = AsyncMock()
    app.add_middleware(AuthGateMiddleware)
    app.add_middleware(LocaleMiddleware)
    app.add_middleware(UserContextMiddleware)
    app.include_router(router)
    return TestClient(app)


def test_auth_401_respects_locale_header(authed_client):
    res = authed_client.get("/api/status", headers={"X-Solar-Locale": "fr"})
    assert res.status_code == 401
    assert res.json()["detail"] == "Non autorisé"


def test_legacy_skip_reason_localized():
    rows = [{"skipped_reason": "already set", "applied": False}]
    out = localize_payload(rows, locale="fr")
    assert out[0]["skipped_reason"] == "engine.skip.already_set"
    assert out[0]["skipped_reason_text"] == "déjà défini"


def test_normalize_skip_key_accepts_key_params_json():
    from app.i18n import normalize_skip_key

    raw = '{"key":"engine.skip.rate_limited","params":{"elapsed":5,"required":60}}'
    assert normalize_skip_key(raw) == "engine.skip.rate_limited"
