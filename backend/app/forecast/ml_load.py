"""Phase 4 (optional): ML load forecasting with gradient boosting.

Replaces the heuristic (dow, hour) profile with a trained model when
scikit-learn is installed and `ML_LOAD_ENABLED=true`. Falls back gracefully:
`available()` reports whether the dependency is present, and a failed train
simply leaves the heuristic forecaster in charge.

Temperature features (raw temp + heating/cooling degree-hours + month) let the
model learn heater/cooler-driven seasonal demand. A `has_temp` flag lets it lean
on month features when temperature is missing for a given timestamp.

The grid stays reactive -- there is NO predictive grid model here either.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from zoneinfo import ZoneInfo

from ..models import LoadForecastPoint, Telemetry, utcnow
from ..tz import to_site_local
from .temperature import cdd, hdd

log = logging.getLogger("forecast.ml_load")

TempLookup = Callable[[datetime], "float | None"]


def available() -> bool:
    try:
        import sklearn  # noqa: F401
        import numpy  # noqa: F401

        return True
    except Exception:  # noqa: BLE001
        return False


def _features(
    dt: datetime,
    temp: float | None,
    hdd_base: float = 18.0,
    cdd_base: float = 24.0,
    site_tz: ZoneInfo | None = None,
) -> list[float]:
    import math

    local = to_site_local(dt, site_tz or ZoneInfo("UTC"))
    hour = local.hour + local.minute / 60.0
    dow = local.weekday()
    month = local.month
    has_temp = 1.0 if temp is not None else 0.0
    t = temp if temp is not None else 0.0
    return [
        math.sin(2 * math.pi * hour / 24.0),
        math.cos(2 * math.pi * hour / 24.0),
        math.sin(2 * math.pi * dow / 7.0),
        math.cos(2 * math.pi * dow / 7.0),
        1.0 if dow >= 5 else 0.0,  # weekend flag
        math.sin(2 * math.pi * month / 12.0),
        math.cos(2 * math.pi * month / 12.0),
        has_temp,
        t,
        hdd(t, hdd_base) if temp is not None else 0.0,
        cdd(t, cdd_base) if temp is not None else 0.0,
    ]


class MLLoadForecaster:
    def __init__(self) -> None:
        self._model = None
        self._trained = False
        self._feature_bases: tuple[float, float] = (18.0, 24.0)

    @property
    def trained(self) -> bool:
        return self._trained

    def train(
        self,
        history: list[Telemetry],
        temp_lookup: TempLookup | None = None,
        hdd_base: float = 18.0,
        cdd_base: float = 24.0,
        site_tz: ZoneInfo | None = None,
    ) -> bool:
        if not available():
            return False
        import numpy as np
        from sklearn.ensemble import HistGradientBoostingRegressor

        xs: list[list[float]] = []
        ys: list[float] = []
        for t in history:
            if t.load_power is None:
                continue
            temp = t.outdoor_temp
            if temp is None and temp_lookup is not None:
                temp = temp_lookup(t.ts)
            xs.append(_features(t.ts, temp, hdd_base, cdd_base, site_tz))
            ys.append(float(t.load_power))

        if len(ys) < 200:  # not enough signal yet
            log.info("ML load: insufficient history (%d rows); skip.", len(ys))
            return False

        model = HistGradientBoostingRegressor(max_iter=200, learning_rate=0.05)
        model.fit(np.array(xs), np.array(ys))
        self._model = model
        self._trained = True
        self._feature_bases = (hdd_base, cdd_base)
        log.info("ML load model trained on %d samples.", len(ys))
        return True

    def export_blob(self) -> dict | None:
        if not self._trained or self._model is None:
            return None
        import base64
        import pickle

        return {
            "blob": base64.b64encode(pickle.dumps(self._model)).decode("ascii"),
            "hdd_base": self._feature_bases[0],
            "cdd_base": self._feature_bases[1],
        }

    def load_blob(self, data: dict) -> bool:
        if not available():
            return False
        import base64
        import pickle

        blob = data.get("blob")
        if not blob:
            return False
        try:
            self._model = pickle.loads(base64.b64decode(blob))
            self._trained = True
            self._feature_bases = (
                float(data.get("hdd_base", 18.0)),
                float(data.get("cdd_base", 24.0)),
            )
            return True
        except Exception as e:  # noqa: BLE001
            log.warning("ML load import failed: %s", e)
            return False

    def forecast(
        self,
        start: datetime | None = None,
        hours: int = 48,
        temp_lookup: TempLookup | None = None,
        hdd_base: float = 18.0,
        cdd_base: float = 24.0,
        site_tz: ZoneInfo | None = None,
    ) -> list[LoadForecastPoint]:
        if not self._trained or self._model is None:
            return []
        import numpy as np

        start = (start or utcnow()).replace(minute=0, second=0, microsecond=0)
        rows = [start + timedelta(hours=i) for i in range(hours)]
        X = np.array(
            [
                _features(
                    ts,
                    temp_lookup(ts) if temp_lookup else None,
                    hdd_base,
                    cdd_base,
                    site_tz,
                )
                for ts in rows
            ]
        )
        preds = self._model.predict(X)
        return [
            LoadForecastPoint(ts=ts, load_power_w=round(float(max(0.0, p)), 1))
            for ts, p in zip(rows, preds)
        ]
