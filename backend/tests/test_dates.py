"""Tests for flexible datetime parsing."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.dates import parse_datetime


def test_iso_date_only():
    dt = parse_datetime("2026-06-24")
    assert dt == datetime(2026, 6, 24, 0, 0, 0)


def test_iso_datetime_z():
    dt = parse_datetime("2026-06-24T15:30:00Z")
    assert dt == datetime(2026, 6, 24, 15, 30, 0, tzinfo=UTC)


def test_ddmmyy_slash():
    dt = parse_datetime("24/06/26")
    assert dt == datetime(2026, 6, 24, 0, 0, 0)


def test_ddmmyyyy_slash_with_time():
    dt = parse_datetime("24/06/2026 15:30")
    assert dt == datetime(2026, 6, 24, 15, 30, 0)


def test_ddmmyy_dash():
    dt = parse_datetime("24-06-2026")
    assert dt == datetime(2026, 6, 24, 0, 0, 0)


def test_empty_rejected():
    with pytest.raises(ValueError, match="empty"):
        parse_datetime("   ")


def test_day_first_ambiguous():
    dt = parse_datetime("03/04/2026")
    assert dt == datetime(2026, 4, 3, 0, 0, 0)
