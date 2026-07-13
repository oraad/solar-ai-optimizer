"""MCP tool registration and in-memory transport."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from app.mcp.backends.orchestrator import OrchestratorBackend
from app.mcp.server import create_mcp_server
from app.models import SystemStatus, utcnow
from tests.conftest import wire_orchestrator_site_tz


def _mock_orch():
    orch = MagicMock()
    orch.build_status.return_value = SystemStatus(
        ha_connected=True,
        telemetry_stale=False,
        telemetry_age_seconds=1.0,
        forecast_misconfigured=False,
        forecast_degraded=False,
        engine_mode="rules",
        engine_active="rules",
        shadow_mode=True,
        paused=False,
        last_updated=utcnow(),
    )
    wire_orchestrator_site_tz(orch)
    orch.collector.latest = None
    orch.forecast.current = None
    orch.latest_grid_stats = None
    orch._plan_flags.return_value = (True, True, True)
    orch.cfg.engine.priority_order = []
    orch.cfg.engine.mode = "rules"
    orch.cfg.engine.enabled = True
    orch.cfg.grid_charge.enabled = True
    orch.cfg.load_shedding.enabled = True
    orch._mpc = None
    orch.shadow_mode = True
    orch.paused = False
    orch.paused_shedding = False
    orch.paused_grid_charge = False
    orch.paused_optimization = False
    orch.override = MagicMock()
    orch.override.model_dump.return_value = {}
    orch.latest_decision = None
    orch.latest_results = []
    orch.latest_shed_results = []
    orch._telemetry_stale.return_value = False
    orch._telemetry_age_seconds.return_value = None
    orch.simulate_decision.return_value = None
    orch.cfg.fail_safe = MagicMock(shutdown_failsafe_enabled=True)
    orch.heartbeat.last_pulse_at = None
    orch.settings = MagicMock()
    orch.settings.mcp_enabled = False
    orch.apply_override = AsyncMock(return_value={"ok": True})
    return orch


@pytest.fixture
def mcp_server():
    backend = OrchestratorBackend(_mock_orch(), rate_limit_key="test")
    return create_mcp_server(lambda: backend, transport="test")


@pytest.mark.asyncio
async def test_mcp_list_tools(mcp_server):
    async with create_connected_server_and_client_session(
        mcp_server._mcp_server
    ) as session:
        tools = await session.list_tools()
    names = {t.name for t in tools.tools}
    assert "solar_get_status" in names
    assert "solar_explain_decision" in names
    assert "solar_apply_override" in names


@pytest.mark.asyncio
async def test_mcp_get_status(mcp_server):
    async with create_connected_server_and_client_session(
        mcp_server._mcp_server
    ) as session:
        result = await session.call_tool("solar_get_status", {})
    assert not result.isError
    assert result.structuredContent is not None


@pytest.mark.asyncio
async def test_mcp_kill_switch_requires_confirm(mcp_server):
    async with create_connected_server_and_client_session(
        mcp_server._mcp_server
    ) as session:
        result = await session.call_tool(
            "solar_apply_override",
            {"kill_switch": True, "confirm_kill_switch": False},
        )
    assert result.isError


@pytest.mark.asyncio
async def test_backend_kill_switch_raises():
    from fastapi import HTTPException
    from app.models import Override

    orch = _mock_orch()
    backend = OrchestratorBackend(orch, rate_limit_key="test2")
    with pytest.raises(HTTPException):
        await backend.apply_override(Override(kill_switch=True), confirm_kill_switch=False)
