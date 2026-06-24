"""Outdoor temperature: forecast horizon + recent history via Open-Meteo.

A single Open-Meteo call (``temperature_2m`` with ``past_days`` + ``forecast_days``)
gives us an hourly temperature series spanning the training window through the
planning horizon. This feeds heating/cooling-degree load modeling so the reserve
floor anticipates heater/cooler demand instead of merely reacting to it.

An optional additive per-hour bias corrects the forecast toward a local HA
outdoor sensor's actuals, mirroring the solar BiasCorrector pattern.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import httpx

from ..config import ForecastConfig
from ..dates import parse_datetime

log = logging.getLogger("forecast.temperature")

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"


def hdd(temp_c: float, base_c: float) -> float:
    """Heating degrees: how far below the balance point (>= 0)."""
    return max(0.0, base_c - temp_c)


def cdd(temp_c: float, base_c: float) -> float:
    """Cooling degrees: how far above the balance point (>= 0)."""
    return max(0.0, temp_c - base_c)


class TemperatureBias:
    """Per-hour-of-day additive offset (actual - forecast), EMA-smoothed."""

    def __init__(self, alpha: float = 0.2, clamp_c: float = 5.0) -> None:
        self._offsets: dict[int, float] = {h: 0.0 for h in range(24)}
        self._alpha = alpha
        self._clamp = clamp_c

    def offset(self, hour: int) -> float:
        return self._offsets.get(hour % 24, 0.0)

    def update(self, hour: int, actual_c: float, forecast_c: float) -> None:
        diff = actual_c - forecast_c
        diff = max(-self._clamp, min(self._clamp, diff))
        prev = self._offsets.get(hour % 24, 0.0)
        self._offsets[hour % 24] = (1 - self._alpha) * prev + self._alpha * diff

    def update_from_pairs(self, pairs: list[tuple[int, float, float]]) -> None:
        for hour, actual_c, forecast_c in pairs:
            self.update(hour, actual_c, forecast_c)

    def as_dict(self) -> dict[int, float]:
        return dict(self._offsets)

    def load_dict(self, d: dict) -> None:
        for k, v in (d or {}).items():
            try:
                self._offsets[int(k) % 24] = float(v)
            except (TypeError, ValueError):
                continue

    def reset(self) -> None:
        self._offsets = {h: 0.0 for h in range(24)}


class TemperatureService:
    def __init__(self, cfg: ForecastConfig) -> None:
        self._cfg = cfg
        self._by_hour_ts: dict[datetime, float] = {}
        self.bias = TemperatureBias()

    def update_config(self, cfg: ForecastConfig) -> None:
        self._cfg = cfg

    @staticmethod
    def _hour_align(ts: datetime) -> datetime:
        return ts.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)

    def _parse_ts(self, t_str: str, utc_offset_seconds: int) -> datetime:
        dt = parse_datetime(t_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc) - timedelta(seconds=utc_offset_seconds)
        return self._hour_align(dt)

    async def refresh(
        self,
        past_days: int = 45,
        forecast_days: int = 3,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        """Fetch the hourly temperature series (history + horizon)."""
        past_days = max(0, min(92, int(past_days)))
        params = {
            "latitude": self._cfg.latitude,
            "longitude": self._cfg.longitude,
            "hourly": "temperature_2m",
            "past_days": past_days,
            "forecast_days": forecast_days,
            "timezone": self._cfg.timezone or "auto",
        }

        async def _fetch(c: httpx.AsyncClient) -> dict:
            resp = await c.get(OPEN_METEO_URL, params=params)
            resp.raise_for_status()
            return resp.json()

        if client is not None:
            data = await _fetch(client)
        else:
            async with httpx.AsyncClient(timeout=20.0) as owned:
                data = await _fetch(owned)
        hourly = data.get("hourly", {})
        times = hourly.get("time", [])
        temps = hourly.get("temperature_2m", [])
        offset = data.get("utc_offset_seconds", 0)
        cache: dict[datetime, float] = {}
        for t_str, temp in zip(times, temps):
            if temp is None:
                continue
            cache[self._parse_ts(t_str, offset)] = float(temp)
        if cache:
            self._by_hour_ts = cache
            log.info("Temperature series refreshed: %d hourly points", len(cache))

    def raw_at(self, ts: datetime) -> float | None:
        """Uncorrected Open-Meteo temperature for the hour containing ``ts``."""
        return self._by_hour_ts.get(self._hour_align(ts))

    def temp_at(self, ts: datetime) -> float | None:
        """Bias-corrected temperature for the hour containing ``ts``."""
        raw = self.raw_at(ts)
        if raw is None:
            return None
        return raw + self.bias.offset(self._hour_align(ts).hour)

    @property
    def available(self) -> bool:
        return bool(self._by_hour_ts)
