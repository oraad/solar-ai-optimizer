"""Config flow tests for Solar AI Optimizer.

Full PHCC (pytest-homeassistant-custom-component) coverage runs in the
dedicated HA integration CI job. These unit tests exercise constants and the
API client without requiring Home Assistant Core.
"""

from __future__ import annotations

import importlib.util
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
    assert manifest["integration_type"] == "service"


def test_domain_and_platforms_without_ha() -> None:
    """Skip const import when Home Assistant is not installed."""
    pytest.importorskip("homeassistant")
    from custom_components.solar_ai_optimizer.const import (  # type: ignore
        DEFAULT_DEBOUNCE_SECONDS,
        DEFAULT_SCAN_INTERVAL,
        DEFAULT_STALE_SECONDS,
        DOMAIN,
        PLATFORMS,
    )

    assert DOMAIN == "solar_ai_optimizer"
    assert len(PLATFORMS) == 3
    assert DEFAULT_STALE_SECONDS == 120
    assert DEFAULT_DEBOUNCE_SECONDS == 120
    assert DEFAULT_SCAN_INTERVAL.total_seconds() == 60


def test_client_strips_trailing_slash() -> None:
    """Host URLs should not keep a trailing slash."""
    pytest.importorskip("aiohttp")
    path = INTEGRATION / "api.py"
    spec = importlib.util.spec_from_file_location(
        "solar_ai_optimizer_api_under_test", path
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    client = module.SolarAiClient(
        host="http://192.168.1.10:8000/",
        access_token="sol_c_test",
        verify_ssl=True,
        session=object(),  # type: ignore[arg-type]
    )
    assert client.host == "http://192.168.1.10:8000"


def test_config_flow_schemas_without_ha() -> None:
    """Pair-only user/reauth schemas and options flow are importable."""
    pytest.importorskip("homeassistant")
    from custom_components.solar_ai_optimizer.config_flow import (  # type: ignore
        OPTIONS_SCHEMA,
        REAUTH_SCHEMA,
        USER_SCHEMA,
        SolarAiConfigFlow,
        SolarAiOptionsFlow,
    )
    from custom_components.solar_ai_optimizer.const import (  # type: ignore
        CONF_HOST,
        CONF_PAIR_CODE,
        CONF_STALE_SECONDS,
    )

    assert CONF_HOST in USER_SCHEMA.schema
    assert CONF_PAIR_CODE in USER_SCHEMA.schema
    assert CONF_PAIR_CODE in REAUTH_SCHEMA.schema
    assert CONF_STALE_SECONDS in OPTIONS_SCHEMA.schema
    assert SolarAiConfigFlow.VERSION == 1
    assert issubclass(SolarAiOptionsFlow, object)


@pytest.mark.asyncio
async def test_config_flow_module_documents_ha_path() -> None:
    """Document the HA integration test path; skip if HA is unavailable."""
    pytest.importorskip("homeassistant")
    from custom_components.solar_ai_optimizer import config_flow  # type: ignore

    assert hasattr(config_flow, "SolarAiConfigFlow")
