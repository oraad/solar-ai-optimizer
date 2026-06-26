"""Site timezone resolution and config validation."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.config import SiteConfig
from app.config_migration import migrate_config_data, migrate_v3_to_v4, migrate_v4_to_v5
from app.tz import fetch_auto_timezone, resolve_site_tz, to_site_local


def test_resolve_site_tz_explicit():
    tz = resolve_site_tz("Africa/Johannesburg")
    assert str(tz) == "Africa/Johannesburg"


def test_resolve_site_tz_auto_with_hint():
    tz = resolve_site_tz("auto", auto_hint="Europe/Berlin")
    assert str(tz) == "Europe/Berlin"


def test_resolve_site_tz_auto_without_hint_falls_back_utc():
    tz = resolve_site_tz("auto")
    assert str(tz) == "UTC"


def test_resolve_site_tz_invalid_falls_back_utc():
    tz = resolve_site_tz("Not/A_Real_Zone")
    assert str(tz) == "UTC"


def test_site_config_rejects_invalid_timezone():
    with pytest.raises(ValueError, match="api.config.timezone"):
        SiteConfig(timezone="Not/A_Real_Zone")


def test_site_config_accepts_auto_and_iana():
    assert SiteConfig(timezone="auto").timezone == "auto"
    assert SiteConfig(timezone="Europe/Paris").timezone == "Europe/Paris"


def test_migrate_v3_to_v4_moves_forecast_timezone():
    out = migrate_v3_to_v4({"forecast": {"timezone": "Africa/Johannesburg", "latitude": 1.0}})
    assert out["site"]["timezone"] == "Africa/Johannesburg"
    assert "timezone" not in out["forecast"]


def test_migrate_v3_to_v4_keeps_existing_site_timezone():
    out = migrate_v3_to_v4(
        {
            "site": {"timezone": "Europe/London"},
            "forecast": {"timezone": "Africa/Johannesburg"},
        }
    )
    assert out["site"]["timezone"] == "Europe/London"
    assert "timezone" not in out["forecast"]


def test_migrate_config_data_on_base_yaml():
    out = migrate_config_data({"forecast": {"timezone": "UTC"}})
    assert out["site"]["timezone"] == "UTC"


def test_migrate_config_data_moves_forecast_coordinates():
    out = migrate_config_data({"forecast": {"latitude": -33.9, "longitude": 18.4}})
    assert out["site"]["latitude"] == -33.9
    assert out["site"]["longitude"] == 18.4
    assert "latitude" not in out["forecast"]


def test_migrate_v4_to_v5_moves_forecast_coordinates():
    out = migrate_v4_to_v5({"forecast": {"latitude": -33.9, "longitude": 18.4}})
    assert out["site"]["latitude"] == -33.9
    assert out["site"]["longitude"] == 18.4


def test_to_site_local():
    utc = datetime(2026, 6, 21, 20, 0, tzinfo=timezone.utc)
    local = to_site_local(utc, resolve_site_tz("Africa/Johannesburg"))
    assert local.hour == 22


@pytest.mark.asyncio
async def test_fetch_auto_timezone_parses_response():
    client = AsyncMock()
    response = MagicMock()
    response.json.return_value = {"timezone": "Africa/Johannesburg"}
    response.raise_for_status = MagicMock()
    client.get = AsyncMock(return_value=response)

    tz = await fetch_auto_timezone(-33.9, 18.4, client)
    assert tz == "Africa/Johannesburg"
