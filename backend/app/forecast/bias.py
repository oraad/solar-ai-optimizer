"""Learned bias correction for the solar forecast.

Maintains a per-hour-of-day multiplicative factor (actual / forecast) updated
with an exponential moving average from the system's own history. This corrects
systematic errors (shading, soiling, model bias) without any external data.
"""

from __future__ import annotations

import logging

log = logging.getLogger("forecast.bias")


class BiasCorrector:
    def __init__(self, alpha: float = 0.2, clamp: tuple[float, float] = (0.3, 2.5)):
        # factor[hour] multiplies the raw forecast for that hour-of-day.
        self._factors: dict[int, float] = {h: 1.0 for h in range(24)}
        self._alpha = alpha
        self._clamp = clamp

    def factor(self, hour: int) -> float:
        return self._factors.get(hour % 24, 1.0)

    def as_dict(self) -> dict[int, float]:
        return dict(self._factors)

    def load_dict(self, d: dict) -> None:
        for k, v in (d or {}).items():
            try:
                self._factors[int(k) % 24] = float(v)
            except (TypeError, ValueError):
                continue

    def update(self, hour: int, actual_w: float, forecast_w: float) -> None:
        """EMA-update the factor for an hour from one (actual, forecast) pair."""
        # Only learn from meaningful daylight production to avoid divide noise.
        if forecast_w < 50 or actual_w < 0:
            return
        ratio = actual_w / forecast_w
        lo, hi = self._clamp
        ratio = max(lo, min(hi, ratio))
        prev = self._factors.get(hour % 24, 1.0)
        self._factors[hour % 24] = (1 - self._alpha) * prev + self._alpha * ratio

    def update_from_pairs(self, pairs: list[tuple[int, float, float]]) -> None:
        for hour, actual_w, forecast_w in pairs:
            self.update(hour, actual_w, forecast_w)
