"""Site timezone behavior in forecast service and load forecaster."""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.config import AppConfig, ForecastConfig, Settings
from app.forecast.load import LoadForecaster
from app.forecast.service import ForecastService
from app.forecast.temperature import TemperatureService
from app.models import SolarForecastPoint, Telemetry


def test_daily_totals_use_site_local_midnight(monkeypatch):
    svc = ForecastService(AppConfig(), Settings())
    svc._cfg.site.timezone = "Africa/Johannesburg"  # noqa: SLF001
    svc._resolved_timezone = "Africa/Johannesburg"  # noqa: SLF001

    # 2026-06-21 22:30 UTC = 2026-06-22 00:30 in Johannesburg (site "tomorrow" at UTC evening)
    now = datetime(2026, 6, 21, 22, 30, tzinfo=timezone.utc)
    monkeypatch.setattr("app.forecast.service.utcnow", lambda: now)

    solar = [
        SolarForecastPoint(
            ts=datetime(2026, 6, 21, 22, 0, tzinfo=timezone.utc),
            pv_power_w=1000.0,
            pv_energy_wh=1000.0,
        ),
        SolarForecastPoint(
            ts=datetime(2026, 6, 22, 22, 0, tzinfo=timezone.utc),
            pv_power_w=2000.0,
            pv_energy_wh=2000.0,
        ),
    ]
    today_kwh, tomorrow_kwh = svc._daily_totals(solar)  # noqa: SLF001
    assert today_kwh == 1.0
    assert tomorrow_kwh == 2.0


def test_load_forecaster_buckets_by_site_local_hour():
    load = LoadForecaster(fallback_w=400.0)
    load.set_site_tz(ZoneInfo("Africa/Johannesburg"))

    # 2026-06-21 22:00 UTC = Sunday 00:00 local; 2026-06-21 08:00 UTC = Sunday 10:00 local
    history = [
        Telemetry(
            ts=datetime(2026, 6, 21, 22, 0, tzinfo=timezone.utc),
            load_power=100.0,
        ),
        Telemetry(
            ts=datetime(2026, 6, 21, 8, 0, tzinfo=timezone.utc),
            load_power=300.0,
        ),
    ]
    load.train(history)

    monday_midnight = load._profile.get((0, 0))  # noqa: SLF001
    sunday_morning = load._profile.get((6, 10))  # noqa: SLF001
    assert monday_midnight == 100.0
    assert sunday_morning == 300.0


def test_temperature_temp_at_uses_site_local_bias_hour():
    temp = TemperatureService(ForecastConfig())
    temp.set_site_timezone("Africa/Johannesburg")
    temp._resolved_timezone = "Africa/Johannesburg"  # noqa: SLF001

    hour_ts = datetime(2026, 6, 21, 22, 0, tzinfo=timezone.utc)
    temp._by_hour_ts = {hour_ts: 20.0}  # noqa: SLF001
    temp.bias._offsets[0] = 5.0  # noqa: SLF001 — site-local midnight offset

    # 22:00 UTC = 00:00 local on June 22
    ts = datetime(2026, 6, 21, 22, 30, tzinfo=timezone.utc)
    assert temp.temp_at(ts) == 25.0


def test_build_status_includes_timezone_fields():
    from unittest.mock import MagicMock

    from app.orchestrator import Orchestrator

    orch = MagicMock()
    orch.cfg = AppConfig()
    orch.cfg.site.timezone = "Europe/Berlin"
    orch.forecast.resolved_timezone = "Europe/Berlin"
    orch.forecast.current = None
    orch.forecast.forecast_provider.return_value = "open-meteo"
    orch.forecast.solcast_configured.return_value = False
    orch.collector.latest = None
    orch.latest_decision = None
    orch.latest_grid_stats = None
    orch.settings = Settings()
    orch.settings.demo_mode = False
    orch.ha.is_reachable.return_value = True
    orch._telemetry_stale.return_value = True
    orch._telemetry_age_seconds.return_value = None
    orch._mpc = None
    orch.override = MagicMock(reserve_soc=None, force_grid_charge=None)
    orch.shadow_mode = True
    orch.paused = False

    status = Orchestrator.build_status(orch)
    assert status.timezone_config == "Europe/Berlin"
    assert status.timezone_resolved == "Europe/Berlin"
