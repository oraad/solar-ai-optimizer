"""Config API serialization for the Settings UI."""

from __future__ import annotations

from app.services.config_view import config_view
from app.config import AppConfig


def test_config_view_includes_site_timezone() -> None:
    cfg = AppConfig(site={"timezone": "Africa/Johannesburg"})
    view = config_view(cfg)
    assert view["site"] == {
        "timezone": "Africa/Johannesburg",
        "latitude": 0.0,
        "longitude": 0.0,
    }


def test_config_view_includes_site_coordinates() -> None:
    cfg = AppConfig(site={"latitude": -33.9, "longitude": 18.4})
    view = config_view(cfg)
    assert view["site"]["latitude"] == -33.9
    assert view["site"]["longitude"] == 18.4
    assert "latitude" not in view["forecast"]
