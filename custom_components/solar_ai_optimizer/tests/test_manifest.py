"""Lightweight tests that do not require a full HA runtime."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
INTEGRATION = ROOT / "custom_components" / "solar_ai_optimizer"


def test_manifest_version_matches_repo() -> None:
    """manifest.json version tracks root VERSION."""
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    manifest = json.loads((INTEGRATION / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["domain"] == "solar_ai_optimizer"
    assert manifest["version"] == version
    assert manifest["config_flow"] is True
    assert "quality_scale" not in manifest


def test_strings_and_translations_match() -> None:
    """translations/en.json stays in sync with strings.json."""
    strings = json.loads((INTEGRATION / "strings.json").read_text(encoding="utf-8"))
    en = json.loads(
        (INTEGRATION / "translations" / "en.json").read_text(encoding="utf-8")
    )
    assert strings == en


def test_hacs_min_version() -> None:
    """hacs.json minimum HA version is 2026.7.0 without zip_release yet."""
    hacs = json.loads((ROOT / "hacs.json").read_text(encoding="utf-8"))
    assert hacs["homeassistant"] == "2026.7.0"
    assert "zip_release" not in hacs


def test_client_strips_trailing_slash() -> None:
    """Host URLs should not keep a trailing slash."""
    pytest.importorskip("aiohttp")
    from custom_components.solar_ai_optimizer.api import SolarAiClient

    client = SolarAiClient(
        host="http://192.168.1.10:8000/",
        access_token="sol_c_test",
        verify_ssl=True,
        session=object(),  # type: ignore[arg-type]
    )
    assert client.host == "http://192.168.1.10:8000"


def test_domain_and_platforms() -> None:
    """Constants expose expected platforms."""
    pytest.importorskip("homeassistant")
    from custom_components.solar_ai_optimizer.const import (
        DEFAULT_SCAN_INTERVAL,
        DOMAIN,
        PLATFORMS,
    )

    assert DOMAIN == "solar_ai_optimizer"
    assert len(PLATFORMS) == 3
    assert DEFAULT_SCAN_INTERVAL.total_seconds() == 60
