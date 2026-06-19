"""Load forecasting from history, temperature-aware.

A baseline profile is built per (day-of-week, hour) average from telemetry. On
top of that, a weather-normalized correction models heater/cooler demand via
heating/cooling degree-hours relative to the recent window mean (so the heating
already embedded in the baseline is not double-counted). When no temperature is
available, a coarse per-month factor is used as a fallback.

Pure-Python (no numpy) so it runs in the lean image; the ML variant lives in
ml_load.py.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from ..models import LoadForecastPoint, Telemetry, utcnow
from .temperature import cdd, hdd

log = logging.getLogger("forecast.load")

TempLookup = Callable[[datetime], "float | None"]


class LoadForecaster:
    def __init__(self, fallback_w: float = 400.0) -> None:
        self._fallback_w = fallback_w
        # profile[(dow, hour)] = average load W
        self._profile: dict[tuple[int, int], float] = {}
        self._recent_overall: float | None = None

        # Temperature model (weather-normalized around the window mean).
        self._k_heat: float = 0.0          # W per heating-degree
        self._k_cool: float = 0.0          # W per cooling-degree
        self._mean_hdd: float = 0.0
        self._mean_cdd: float = 0.0
        self._month_factors: dict[int, float] = {}

        # Config (set via configure()).
        self._hdd_base = 18.0
        self._cdd_base = 24.0
        self._min_load_fraction = 0.8
        self._use_month_fallback = True

        self._temp_provider: TempLookup | None = None

    def configure(
        self,
        hdd_base: float,
        cdd_base: float,
        min_load_fraction: float,
        use_month_fallback: bool,
    ) -> None:
        self._hdd_base = hdd_base
        self._cdd_base = cdd_base
        self._min_load_fraction = min_load_fraction
        self._use_month_fallback = use_month_fallback

    def set_temp_provider(self, fn: TempLookup | None) -> None:
        self._temp_provider = fn

    # --------------------------------------------------------------- training --
    def train(self, history: list[Telemetry], temp_lookup: TempLookup | None = None) -> None:
        """Build the (dow, hour) profile and the temperature/month corrections."""
        buckets: dict[tuple[int, int], list[float]] = defaultdict(list)
        recent: list[float] = []
        cutoff_recent = utcnow() - timedelta(days=3)
        month_loads: dict[int, list[float]] = defaultdict(list)
        all_loads: list[float] = []

        for t in history:
            if t.load_power is None:
                continue
            ts = t.ts.astimezone(timezone.utc)
            buckets[(ts.weekday(), ts.hour)].append(t.load_power)
            month_loads[ts.month].append(t.load_power)
            all_loads.append(t.load_power)
            if ts >= cutoff_recent:
                recent.append(t.load_power)

        self._profile = {
            key: sum(vals) / len(vals) for key, vals in buckets.items() if vals
        }
        self._recent_overall = (sum(recent) / len(recent)) if recent else None

        self._train_month_factors(month_loads, all_loads)
        self._train_temperature(history, temp_lookup)

        if self._profile:
            log.info(
                "Load profile trained: %d buckets, k_heat=%.2f k_cool=%.2f",
                len(self._profile),
                self._k_heat,
                self._k_cool,
            )

    def _train_month_factors(
        self, month_loads: dict[int, list[float]], all_loads: list[float]
    ) -> None:
        self._month_factors = {}
        if not all_loads:
            return
        overall = sum(all_loads) / len(all_loads)
        if overall <= 0:
            return
        for month, vals in month_loads.items():
            if not vals:
                continue
            factor = (sum(vals) / len(vals)) / overall
            self._month_factors[month] = max(0.5, min(2.0, factor))

    def _train_temperature(
        self, history: list[Telemetry], temp_lookup: TempLookup | None
    ) -> None:
        """Estimate k_heat/k_cool by single-variable LSQ of the baseline residual
        on degree-hours centered at the window mean (weather normalization)."""
        self._k_heat = self._k_cool = 0.0
        self._mean_hdd = self._mean_cdd = 0.0
        if temp_lookup is None or not self._profile:
            return

        hdds: list[float] = []
        cdds: list[float] = []
        resid: list[float] = []
        for t in history:
            if t.load_power is None:
                continue
            temp = t.outdoor_temp if t.outdoor_temp is not None else temp_lookup(t.ts)
            if temp is None:
                continue
            ts = t.ts.astimezone(timezone.utc)
            base = self._profile.get((ts.weekday(), ts.hour))
            if base is None:
                continue
            hdds.append(hdd(temp, self._hdd_base))
            cdds.append(cdd(temp, self._cdd_base))
            resid.append(t.load_power - base)

        n = len(resid)
        if n < 24:  # not enough temperature-paired samples yet
            return
        self._mean_hdd = sum(hdds) / n
        self._mean_cdd = sum(cdds) / n
        self._k_heat = self._lsq_slope(hdds, self._mean_hdd, resid)
        self._k_cool = self._lsq_slope(cdds, self._mean_cdd, resid)
        # Heating/cooling load should not be negative-sloped; clamp to >= 0.
        self._k_heat = max(0.0, self._k_heat)
        self._k_cool = max(0.0, self._k_cool)

    @staticmethod
    def _lsq_slope(xs: list[float], xbar: float, ys: list[float]) -> float:
        num = 0.0
        den = 0.0
        for x, y in zip(xs, ys):
            xc = x - xbar
            num += xc * y
            den += xc * xc
        return num / den if den > 1e-9 else 0.0

    # ------------------------------------------------------------ persistence --
    def export(self) -> dict:
        return {
            "profile": {f"{k[0]}:{k[1]}": v for k, v in self._profile.items()},
            "recent_overall": self._recent_overall,
            "k_heat": self._k_heat,
            "k_cool": self._k_cool,
            "mean_hdd": self._mean_hdd,
            "mean_cdd": self._mean_cdd,
            "month_factors": {str(m): f for m, f in self._month_factors.items()},
        }

    def load_profile(self, d: dict) -> None:
        prof = (d or {}).get("profile", {})
        parsed: dict[tuple[int, int], float] = {}
        for key, v in prof.items():
            try:
                dow, hour = (int(x) for x in str(key).split(":"))
                parsed[(dow, hour)] = float(v)
            except (TypeError, ValueError):
                continue
        if parsed:
            self._profile = parsed
        ro = (d or {}).get("recent_overall")
        if ro is not None:
            self._recent_overall = float(ro)
        self._k_heat = float(d.get("k_heat", self._k_heat) or 0.0)
        self._k_cool = float(d.get("k_cool", self._k_cool) or 0.0)
        self._mean_hdd = float(d.get("mean_hdd", self._mean_hdd) or 0.0)
        self._mean_cdd = float(d.get("mean_cdd", self._mean_cdd) or 0.0)
        mf = (d or {}).get("month_factors", {})
        parsed_mf: dict[int, float] = {}
        for k, v in mf.items():
            try:
                parsed_mf[int(k)] = float(v)
            except (TypeError, ValueError):
                continue
        if parsed_mf:
            self._month_factors = parsed_mf

    # ------------------------------------------------------------ prediction --
    def _baseline_for(self, dt: datetime) -> float:
        key = (dt.weekday(), dt.hour)
        if key in self._profile:
            return self._profile[key]
        if self._recent_overall is not None:
            return self._recent_overall
        return self._fallback_w

    def _value_for(self, dt: datetime) -> float:
        dt = dt.astimezone(timezone.utc)
        baseline = self._baseline_for(dt)
        value = baseline

        temp = self._temp_provider(dt) if self._temp_provider else None
        if temp is not None and (self._k_heat or self._k_cool):
            # Weather normalization: adjust by degree-hours vs the window mean.
            value = baseline + self._k_heat * (hdd(temp, self._hdd_base) - self._mean_hdd)
            value += self._k_cool * (cdd(temp, self._cdd_base) - self._mean_cdd)
        elif self._use_month_fallback and self._month_factors:
            value = baseline * self._month_factors.get(dt.month, 1.0)

        # Resilience floor: never let a mild forecast shrink load too far.
        floor = self._min_load_fraction * baseline
        return max(0.0, max(value, floor))

    def forecast(
        self, start: datetime | None = None, hours: int = 48
    ) -> list[LoadForecastPoint]:
        start = (start or utcnow()).replace(minute=0, second=0, microsecond=0)
        points: list[LoadForecastPoint] = []
        for i in range(hours):
            ts = start + timedelta(hours=i)
            points.append(
                LoadForecastPoint(ts=ts, load_power_w=round(self._value_for(ts), 1))
            )
        return points

    def expected_overnight_wh(self, hours: float) -> float:
        """Energy (Wh) the load is expected to consume over the next `hours`."""
        now = utcnow()
        total = 0.0
        whole = int(hours)
        for i in range(whole):
            total += self._value_for(now + timedelta(hours=i))
        frac = hours - whole
        if frac > 0:
            total += self._value_for(now + timedelta(hours=whole)) * frac
        return total
