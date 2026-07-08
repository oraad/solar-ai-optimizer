"""API site-timezone serialization tests."""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.i18n.serialize import apply_site_timezone, localize_payload
from app.tz import format_site_local_iso, is_utc_serializable, parse_api_utc


def test_is_utc_serializable():
    assert is_utc_serializable("2026-07-08T05:27:00Z") is True
    assert is_utc_serializable("2026-07-08T05:27:00+00:00") is True
    assert is_utc_serializable("2026-07-08T05:27:00") is True
    assert is_utc_serializable("2026-07-08T08:27:00+03:00") is False


def test_format_site_local_iso():
    utc = datetime(2026, 7, 8, 5, 27, tzinfo=timezone.utc)
    out = format_site_local_iso(utc, ZoneInfo("Asia/Riyadh"))
    assert out == "2026-07-08T08:27:00+03:00"


def test_parse_api_utc_naive():
    dt = parse_api_utc("2026-07-08T05:27:00")
    assert dt.tzinfo == timezone.utc
    assert dt.hour == 5


def test_apply_site_timezone_nested():
    tz = ZoneInfo("Asia/Riyadh")
    payload = {
        "last_updated": "2026-07-08T05:27:00+00:00",
        "nested": {"ts": "2026-07-08T05:27:00"},
    }
    out = apply_site_timezone(payload, tz)
    assert out["last_updated"] == "2026-07-08T08:27:00+03:00"
    assert out["nested"]["ts"] == "2026-07-08T08:27:00+03:00"


def test_apply_site_timezone_idempotent():
    tz = ZoneInfo("Asia/Riyadh")
    localized = "2026-07-08T08:27:00+03:00"
    out = apply_site_timezone({"ts": localized}, tz)
    assert out["ts"] == localized


def test_localize_payload_with_site_tz():
    tz = ZoneInfo("UTC")
    out = localize_payload({"time": "2026-07-08T05:27:00Z"}, site_tz=tz)
    assert out["time"] == "2026-07-08T05:27:00+00:00"
