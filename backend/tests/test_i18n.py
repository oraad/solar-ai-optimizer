"""i18n core behavior."""

from __future__ import annotations

from app.i18n import get_locale, msg, set_locale, t
from app.i18n.serialize import expand_msg


def test_t_interpolation_en():
    assert "52%" in t("engine.grid.reserve_met", {"target": 52, "soc": 48}, locale="en")


def test_t_french_fallback():
    token = set_locale("fr")
    try:
        assert "Non autorisé" == t("api.auth.unauthorized")
    finally:
        from app.i18n import reset_locale

        reset_locale(token)


def test_msg_expand_reserve_driver():
    m = msg(
        "engine.reserve.main",
        target=50,
        driver="engine.reserve.driver_solar_bridge",
        autonomy=40,
        hours=12,
        load=400,
        bridge=45,
        bridge_kwh=1.2,
        buffer=15,
        extra_cold="",
        extra_heat="",
        extra_degraded="",
        hdh=0,
        cdh=0,
    )
    text = expand_msg(m, locale="en")
    assert "50%" in text
    assert "solar-bridge" in text
