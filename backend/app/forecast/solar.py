"""Solar PV forecasting via Open-Meteo (default) or Solcast (optional).

Open-Meteo is free and key-less. We request global tilted irradiance (GTI) per
array using its tilt/azimuth, then convert to PV power with a performance ratio.
A learned bias corrector refines the estimate from the site's own history.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

import httpx
from dateutil import parser as dtparser

from ..config import ForecastConfig
from ..models import SolarForecastPoint
from .bias import BiasCorrector

log = logging.getLogger("forecast.solar")

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
PERFORMANCE_RATIO = 0.85  # inverter + wiring + temperature losses


def _to_openmeteo_azimuth(config_azimuth: float) -> float:
    """Convert config azimuth (0=N, 90=E, 180=S, 270=W) to Open-Meteo (0=S)."""
    az = config_azimuth - 180.0
    while az > 180:
        az -= 360
    while az < -180:
        az += 360
    return az


class SolarForecaster:
    def __init__(
        self,
        cfg: ForecastConfig,
        bias: BiasCorrector,
        solcast_key: str = "",
        solcast_resource: str = "",
    ) -> None:
        self._cfg = cfg
        self._bias = bias
        self._solcast_key = solcast_key
        self._solcast_resource = solcast_resource
        # Cache of last raw (pre-bias) forecast keyed by hour timestamp, for the
        # bias learner to compare against actuals later.
        self.last_raw_by_ts: dict[datetime, float] = {}

    def set_solcast_credentials(self, key: str, resource: str) -> None:
        self._solcast_key = key or ""
        self._solcast_resource = resource or ""

    def solcast_configured(self) -> bool:
        return bool(self._solcast_key and self._solcast_resource)

    async def forecast(
        self, client: httpx.AsyncClient | None = None
    ) -> list[SolarForecastPoint]:
        if self._cfg.provider == "solcast":
            if self.solcast_configured():
                try:
                    return await self._forecast_solcast()
                except Exception as e:  # noqa: BLE001
                    log.warning("Solcast failed (%s); falling back to Open-Meteo", e)
            else:
                log.warning(
                    "Solcast provider selected but SOLCAST_API_KEY or "
                    "SOLCAST_RESOURCE_ID is missing"
                )
        return await self._forecast_open_meteo(client=client)

    # ----------------------------------------------------------- Open-Meteo --
    async def _forecast_open_meteo(
        self, client: httpx.AsyncClient | None = None
    ) -> list[SolarForecastPoint]:
        # Accumulate GTI-derived power across all arrays, hour-aligned.
        power_by_ts: dict[datetime, float] = {}

        async def run(c: httpx.AsyncClient) -> dict[datetime, float]:
            merged: dict[datetime, float] = {}

            async def fetch_array(array) -> dict[datetime, float]:  # noqa: ANN001
                params = {
                    "latitude": self._cfg.latitude,
                    "longitude": self._cfg.longitude,
                    "hourly": "global_tilted_irradiance,cloudcover",
                    "tilt": array.tilt,
                    "azimuth": _to_openmeteo_azimuth(array.azimuth),
                    "forecast_days": 3,
                    "timezone": self._cfg.timezone or "auto",
                }
                resp = await c.get(OPEN_METEO_URL, params=params)
                resp.raise_for_status()
                data = resp.json()
                hourly = data.get("hourly", {})
                times = hourly.get("time", [])
                gti = hourly.get("global_tilted_irradiance", [])
                out: dict[datetime, float] = {}
                for t_str, irr in zip(times, gti):
                    if irr is None:
                        continue
                    ts = self._parse_ts(t_str, data.get("utc_offset_seconds", 0))
                    p = array.kwp * 1000.0 * (float(irr) / 1000.0) * PERFORMANCE_RATIO
                    out[ts] = out.get(ts, 0.0) + max(0.0, p)
                return out

            results = await asyncio.gather(
                *[fetch_array(array) for array in self._cfg.arrays],
                return_exceptions=True,
            )
            for result in results:
                if isinstance(result, Exception):
                    raise result
                for ts, p in result.items():
                    merged[ts] = merged.get(ts, 0.0) + p
            return merged

        if client is not None:
            power_by_ts = await run(client)
        else:
            async with httpx.AsyncClient(timeout=20.0) as owned:
                power_by_ts = await run(owned)

        return self._build_points(power_by_ts)

    @staticmethod
    def _hour_align(ts: datetime) -> datetime:
        return ts.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)

    def _parse_ts(self, t_str: str, utc_offset_seconds: int) -> datetime:
        dt = dtparser.parse(t_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc) - timedelta(seconds=utc_offset_seconds)
        return self._hour_align(dt)

    # -------------------------------------------------------------- Solcast --
    async def _forecast_solcast(self) -> list[SolarForecastPoint]:
        url = (
            f"https://api.solcast.com.au/rooftop_sites/"
            f"{self._solcast_resource}/forecasts"
        )
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(
                url,
                params={"format": "json", "hours": 72},
                headers={"Authorization": f"Bearer {self._solcast_key}"},
            )
            resp.raise_for_status()
            data = resp.json()
        power_by_ts: dict[datetime, float] = {}
        for item in data.get("forecasts", []):
            ts = self._hour_align(
                dtparser.parse(item["period_end"]).astimezone(timezone.utc)
            )
            kw = float(item.get("pv_estimate", 0.0))
            power_by_ts[ts] = kw * 1000.0
        return self._build_points(power_by_ts)

    # ---------------------------------------------------------------- shared --
    def _build_points(
        self, power_by_ts: dict[datetime, float]
    ) -> list[SolarForecastPoint]:
        self.last_raw_by_ts = dict(power_by_ts)
        points: list[SolarForecastPoint] = []
        ordered = sorted(power_by_ts.items())
        for ts, raw_w in ordered:
            corrected = raw_w * self._bias.factor(ts.astimezone(timezone.utc).hour)
            # 1h step energy (Wh). Trapezoidal would need neighbours; hourly ~ W*1h.
            points.append(
                SolarForecastPoint(
                    ts=ts,
                    pv_power_w=round(corrected, 1),
                    pv_energy_wh=round(corrected, 1),
                )
            )
        return points
