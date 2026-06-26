"""Config API serialization for the Settings UI."""

from __future__ import annotations

from app.api.routes import _config_view
from app.config import AppConfig


def test_config_view_includes_site_timezone() -> None:
    cfg = AppConfig(site={"timezone": "Africa/Johannesburg"})
    view = _config_view(cfg)
    assert view["site"] == {"timezone": "Africa/Johannesburg"}
