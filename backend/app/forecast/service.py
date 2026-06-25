"""ForecastService: orchestrates solar + load + bias into a ForecastBundle."""

from __future__ import annotations

import asyncio
import json
import logging

import httpx
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..config import AppConfig, Settings
from ..i18n import msg
from ..models import ForecastBundle, Telemetry, TemperaturePoint, utcnow
from ..storage import repo
from .bias import BiasCorrector
from .load import LoadForecaster
from .solar import SolarForecaster
from .temperature import TemperatureService, cdd, hdd

log = logging.getLogger("forecast.service")


class ForecastService:
    def __init__(self, cfg: AppConfig, settings: Settings) -> None:
        self._cfg = cfg
        self._settings = settings
        self._bias = BiasCorrector()
        self._solar = SolarForecaster(
            cfg.forecast,
            self._bias,
            solcast_key=settings.solcast_api_key,
            solcast_resource=settings.solcast_resource_id,
        )
        self._load = LoadForecaster(fallback_w=cfg.reserve.critical_load_w)
        self._temp = TemperatureService(cfg.forecast)
        self._apply_temp_config()
        self._current: ForecastBundle | None = None
        self._refresh_lock = asyncio.Lock()
        self._ml_import_locked = False

        # Optional ML load forecaster (Phase 4); used only if enabled + available.
        self._ml_load = None
        self._ml_enabled = settings.ml_load_enabled
        if self._ml_enabled:
            try:
                from .ml_load import MLLoadForecaster, available

                if available():
                    self._ml_load = MLLoadForecaster()
                    log.info("ML load forecasting enabled.")
                else:
                    log.warning(
                        "ML_LOAD_ENABLED set but scikit-learn missing; using heuristic."
                    )
            except Exception as e:  # noqa: BLE001
                log.warning("ML load init failed (%s); using heuristic.", e)

    def solcast_configured(self) -> bool:
        return self._solar.solcast_configured()

    def forecast_provider(self) -> str:
        return self._cfg.forecast.provider

    @property
    def load_forecaster(self) -> LoadForecaster:
        return self._load

    def _apply_temp_config(self) -> None:
        tc = self._cfg.forecast.temperature
        self._load.configure(
            hdd_base=tc.hdd_base_c,
            cdd_base=tc.cdd_base_c,
            min_load_fraction=tc.min_load_fraction,
            use_month_fallback=tc.use_month_fallback and tc.enabled,
        )

    def update_config(self, cfg: AppConfig) -> None:
        """Hot-update config without losing learned state."""
        self._cfg = cfg
        self._solar._cfg = cfg.forecast  # noqa: SLF001
        self._solar.set_solcast_credentials(
            self._settings.solcast_api_key,
            self._settings.solcast_resource_id,
        )
        self._load._fallback_w = cfg.reserve.critical_load_w  # noqa: SLF001
        self._temp.update_config(cfg.forecast)
        self._apply_temp_config()

    def _ensure_ml_load(self) -> None:
        if self._ml_load is not None:
            return
        from .ml_load import MLLoadForecaster, available

        if not available():
            raise ValueError(
                "ml_load blob requires scikit-learn; install extras or enable ML_LOAD_ENABLED"
            )
        self._ml_load = MLLoadForecaster()
        log.warning("ML load forecaster lazily initialised from import.")

    # ----------------------------------------------------- model import/export --
    def export_model(self) -> dict:
        """Serialise the learned state (bias factors + load profile + temp bias)."""
        payload: dict = {
            "version": 3,
            "ml_import_locked": self._ml_import_locked,
            "bias": {str(k): v for k, v in self._bias.as_dict().items()},
            "load": self._load.export(),
            "temp_bias": {str(k): v for k, v in self._temp.bias.as_dict().items()},
        }
        if self._ml_load is not None:
            ml = self._ml_load.export_blob()
            if ml:
                payload["ml_load"] = ml
        return payload

    def import_model(self, data: dict) -> None:
        self._bias.load_dict(data.get("bias", {}))
        self._load.load_profile(data.get("load", {}))
        self._temp.bias.load_dict(data.get("temp_bias", {}))
        self._ml_import_locked = bool(data.get("ml_import_locked", False))
        if data.get("ml_load"):
            self._ensure_ml_load()
            self._ml_load.load_blob(data["ml_load"])
            self._ml_import_locked = True
        elif "ml_load" not in data and not data.get("ml_import_locked"):
            self._ml_import_locked = False
        log.info("Learned model imported (ml_import_locked=%s).", self._ml_import_locked)

    def save_model(self, path: str | Path) -> None:
        try:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(self.export_model()), encoding="utf-8")
        except Exception as e:  # noqa: BLE001
            log.debug("save_model failed: %s", e)

    def load_model(self, path: str | Path) -> bool:
        p = Path(path)
        if not p.exists():
            return False
        try:
            self.import_model(json.loads(p.read_text(encoding="utf-8")))
            return True
        except Exception as e:  # noqa: BLE001
            log.warning("load_model failed: %s", e)
            return False

    @property
    def ml_import_locked(self) -> bool:
        return self._ml_import_locked

    async def retrain_ml_load(self) -> bool:
        """Clear import lock and retrain ML load model from telemetry history."""
        async with self._refresh_lock:
            self._ml_import_locked = False
            if self._ml_load is None:
                return False
            tc = self._cfg.forecast.temperature
            window_days = max(21, tc.training_days)
            history = await repo.get_telemetry_since(
                utcnow() - timedelta(days=window_days)
            )
            temp_lookup = self._temp.temp_at if self._temp.available else None
            trained = self._ml_load.train(
                history,
                temp_lookup=temp_lookup,
                hdd_base=tc.hdd_base_c,
                cdd_base=tc.cdd_base_c,
            )
            return bool(trained)

    @property
    def current(self) -> ForecastBundle | None:
        return self._current

    async def refresh(self) -> ForecastBundle:
        """Recompute the full forecast bundle. Resilient to provider failures."""
        async with self._refresh_lock:
            return await self._refresh_unlocked()

    async def _refresh_unlocked(self) -> ForecastBundle:
        degraded_reasons: list[str] = []
        fc = self._cfg.forecast
        if fc.provider == "solcast" and not self.solcast_configured():
            degraded_reasons.append(
                msg("forecast.degraded.solcast_misconfigured")
            )
        if not fc.location_configured:
            degraded_reasons.append(
                msg("forecast.degraded.location_missing")
            )
            log.warning(
                "Forecast location is 0,0 — set latitude/longitude in Settings."
            )
        tc = fc.temperature
        # Use the temperature training window so month/regression have enough data.
        window_days = max(21, tc.training_days)
        history = await repo.get_telemetry_since(utcnow() - timedelta(days=window_days))

        temp_lookup = None
        solar_stale = False
        solar: list = []

        self._update_bias_from_history(history)

        if fc.location_configured:
            async with httpx.AsyncClient(timeout=20.0) as client:
                names: list[str] = []
                coros = []
                if tc.enabled:
                    names.append("temp")
                    coros.append(
                        self._temp.refresh(
                            past_days=tc.training_days,
                            forecast_days=3,
                            client=client,
                        )
                    )
                names.append("solar")
                coros.append(self._solar.forecast(client=client))
                results = await asyncio.gather(*coros, return_exceptions=True)
                for name, result in zip(names, results, strict=True):
                    if isinstance(result, Exception):
                        if name == "temp":
                            log.warning(
                                "Temperature refresh failed (%s); proceeding without.",
                                result,
                            )
                            degraded_reasons.append(
                                msg(
                                    "forecast.degraded.temperature_failed",
                                    error=str(result),
                                )
                            )
                        else:
                            log.warning("Solar forecast failed (%s); keeping previous", result)
                            solar = self._current.solar if self._current else []
                            solar_stale = True
                            degraded_reasons.append(
                                msg(
                                    "forecast.degraded.solar_failed",
                                    error=str(result),
                                )
                            )
                    elif name == "solar":
                        solar = result
                    elif self._temp.available:
                        temp_lookup = self._temp.temp_at
                        self._update_temp_bias_from_history(history)
        else:
            solar = self._current.solar if self._current else []
            solar_stale = True

        self._load.set_temp_provider(temp_lookup)

        load: list = []
        ml_ok = False
        if self._ml_load is not None:
            try:
                use_imported = self._ml_import_locked and self._ml_load.trained
                if use_imported:
                    load = self._ml_load.forecast(
                        hours=48,
                        temp_lookup=temp_lookup,
                        hdd_base=tc.hdd_base_c,
                        cdd_base=tc.cdd_base_c,
                    )
                    ml_ok = bool(load)
                elif self._ml_load.train(
                    history,
                    temp_lookup=temp_lookup,
                    hdd_base=tc.hdd_base_c,
                    cdd_base=tc.cdd_base_c,
                ):
                    load = self._ml_load.forecast(
                        hours=48,
                        temp_lookup=temp_lookup,
                        hdd_base=tc.hdd_base_c,
                        cdd_base=tc.cdd_base_c,
                    )
                    ml_ok = bool(load)
            except Exception as e:  # noqa: BLE001
                log.warning("ML load forecast failed (%s); using heuristic.", e)
        if not ml_ok:
            self._load.train(history, temp_lookup=temp_lookup)
            load = self._load.forecast(hours=48)

        if solar_stale and solar:
            degraded_reasons.append(msg("forecast.degraded.stale_solar"))

        temperature, hdh, cdh = self._temperature_points(temp_lookup)

        today_kwh, tomorrow_kwh = self._daily_totals(solar)
        bundle = ForecastBundle(
            generated_at=utcnow(),
            solar=solar,
            load=load,
            temperature=temperature,
            solar_today_kwh=round(today_kwh, 2),
            solar_tomorrow_kwh=round(tomorrow_kwh, 2),
            cloudy_tomorrow=self._is_cloudy(tomorrow_kwh),
            heating_degree_hours_24h=round(hdh, 1),
            cooling_degree_hours_24h=round(cdh, 1),
            degraded=bool(degraded_reasons),
            degraded_reasons=degraded_reasons,
        )
        self._current = bundle
        log.info(
            "Forecast refreshed: today=%.1f kWh tomorrow=%.1f kWh cloudy=%s",
            today_kwh,
            tomorrow_kwh,
            bundle.cloudy_tomorrow,
        )
        return bundle

    def _temperature_points(
        self, temp_lookup
    ) -> tuple[list[TemperaturePoint], float, float]:
        """Hourly temperature series for the next 48h + 24h degree-hour totals."""
        if temp_lookup is None or not self._temp.available:
            return [], 0.0, 0.0
        tc = self._cfg.forecast.temperature
        start = utcnow().replace(minute=0, second=0, microsecond=0)
        points: list[TemperaturePoint] = []
        hdh = cdh = 0.0
        for i in range(48):
            ts = start + timedelta(hours=i)
            t = temp_lookup(ts)
            if t is None:
                continue
            points.append(TemperaturePoint(ts=ts, temp_c=round(t, 1)))
            if i < 24:
                hdh += hdd(t, tc.hdd_base_c)
                cdh += cdd(t, tc.cdd_base_c)
        return points, hdh, cdh

    def _update_temp_bias_from_history(self, history: list[Telemetry]) -> None:
        """EMA the Open-Meteo vs HA-sensor temperature offset per hour-of-day."""
        pairs: list[tuple[int, float, float]] = []
        for t in history:
            if t.outdoor_temp is None:
                continue
            raw = self._temp.raw_at(t.ts)
            if raw is None:
                continue
            hour = t.ts.astimezone(timezone.utc).hour
            pairs.append((hour, float(t.outdoor_temp), raw))
        if pairs:
            self._temp.bias.update_from_pairs(pairs)
            log.debug("Temp bias updated from %d hour pairs", len(pairs))

    def _daily_totals(self, solar: list) -> tuple[float, float]:
        today = utcnow().astimezone(timezone.utc).date()
        tomorrow = today + timedelta(days=1)
        totals: dict[object, float] = defaultdict(float)
        for p in solar:
            d = p.ts.astimezone(timezone.utc).date()
            totals[d] += p.pv_energy_wh / 1000.0  # Wh -> kWh
        return totals.get(today, 0.0), totals.get(tomorrow, 0.0)

    def _is_cloudy(self, tomorrow_kwh: float) -> bool:
        from .helpers import expected_clear_sky_kwh, total_kwp

        expected_clear = expected_clear_sky_kwh(total_kwp(self._cfg.forecast.arrays))
        return tomorrow_kwh < 0.5 * expected_clear

    def _update_bias_from_history(self, history: list[Telemetry]) -> None:
        raw = self._solar.last_raw_by_ts
        if not raw:
            return
        # Average actual PV per hour-bucket timestamp.
        actual_by_hour_ts: dict[datetime, list[float]] = defaultdict(list)
        for t in history:
            if t.pv_power is None:
                continue
            hour_ts = t.ts.astimezone(timezone.utc).replace(
                minute=0, second=0, microsecond=0
            )
            actual_by_hour_ts[hour_ts].append(t.pv_power)

        pairs: list[tuple[int, float, float]] = []
        for hour_ts, fc_w in raw.items():
            key = hour_ts.astimezone(timezone.utc).replace(
                minute=0, second=0, microsecond=0
            )
            if key in actual_by_hour_ts:
                acts = actual_by_hour_ts[key]
                avg_actual = sum(acts) / len(acts)
                pairs.append((key.hour, avg_actual, fc_w))
        if pairs:
            self._bias.update_from_pairs(pairs)
            log.debug("Bias updated from %d hour pairs", len(pairs))
