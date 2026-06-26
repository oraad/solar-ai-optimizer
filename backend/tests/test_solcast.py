"""Solcast solar provider gating."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import ForecastConfig, PvArray, SiteConfig
from app.forecast.bias import BiasCorrector
from app.forecast.solar import SolarForecaster


def _forecaster(provider: str, key: str = "", resource: str = "") -> SolarForecaster:
    cfg = ForecastConfig(
        provider=provider,  # type: ignore[arg-type]
        arrays=[PvArray(kwp=5.0)],
    )
    site = SiteConfig(latitude=-33.9, longitude=18.4)
    return SolarForecaster(cfg, site, BiasCorrector(), solcast_key=key, solcast_resource=resource)


def test_solcast_configured_requires_key_and_resource():
    f = _forecaster("solcast", key="k", resource="")
    assert f.solcast_configured() is False
    f.set_solcast_credentials("k", "site-1")
    assert f.solcast_configured() is True


@pytest.mark.asyncio
async def test_open_meteo_never_calls_solcast():
    f = _forecaster("open-meteo", key="k", resource="site-1")
    with patch.object(f, "_forecast_solcast", new_callable=AsyncMock) as solcast:
        with patch.object(f, "_forecast_open_meteo", new_callable=AsyncMock) as om:
            om.return_value = []
            await f.forecast()
    solcast.assert_not_awaited()
    om.assert_awaited_once()


@pytest.mark.asyncio
async def test_solcast_missing_resource_falls_back_to_open_meteo():
    f = _forecaster("solcast", key="k", resource="")
    with patch.object(f, "_forecast_solcast", new_callable=AsyncMock) as solcast:
        with patch.object(f, "_forecast_open_meteo", new_callable=AsyncMock) as om:
            om.return_value = []
            await f.forecast()
    solcast.assert_not_awaited()
    om.assert_awaited_once()


@pytest.mark.asyncio
async def test_solcast_with_credentials_calls_api():
    f = _forecaster("solcast", key="k", resource="site-1")
    with patch.object(f, "_forecast_solcast", new_callable=AsyncMock) as solcast:
        solcast.return_value = []
        result = await f.forecast()
    solcast.assert_awaited_once()
    assert result == []
