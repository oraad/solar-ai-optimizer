"""Forecasting: solar (Open-Meteo/Solcast) + load profile + bias correction.

Note: there is deliberately NO grid forecast. The grid is treated as a reactive,
opportunistic resource only (see grid module).
"""

from .service import ForecastService

__all__ = ["ForecastService"]
