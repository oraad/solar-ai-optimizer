"""HTTP client SolarBackend for stdio MCP (talks to running solar API)."""

from __future__ import annotations

import os
import uuid
from typing import Any

import httpx

from ..models import Override


class ApiBackend:
    """MCP backend via REST API."""

    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        *,
        request_id: str | None = None,
    ) -> None:
        self._base = (base_url or os.environ.get("SOLAR_API_URL", "http://127.0.0.1:8000")).rstrip(
            "/"
        )
        self._token = token or os.environ.get("MCP_TOKEN") or os.environ.get("API_TOKEN") or ""
        self._request_id = request_id or str(uuid.uuid4())
        self._client: httpx.AsyncClient | None = None

    def _headers(self) -> dict[str, str]:
        headers = {"X-Request-ID": self._request_id}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._base,
                headers=self._headers(),
                timeout=60.0,
            )
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict | None = None,
        params: dict | None = None,
    ) -> Any:
        client = await self._get_client()
        res = await client.request(method, path, json=json, params=params)
        res.raise_for_status()
        return res.json()

    async def get_status(self) -> dict[str, Any]:
        return await self._request("GET", "/api/status")

    async def get_health(self) -> dict[str, Any]:
        return await self._request("GET", "/api/health")

    async def explain_decision(self, sections: str | None = None) -> dict[str, Any]:
        params = {"sections": sections} if sections else None
        return await self._request("GET", "/api/debug/trace", params=params)

    async def simulate_decision(self) -> dict[str, Any]:
        return await self._request("POST", "/api/debug/simulate")

    async def get_engine_config(self) -> dict[str, Any]:
        return await self._request("GET", "/api/config")

    async def get_forecast(self) -> dict[str, Any]:
        return await self._request("GET", "/api/forecast")

    async def get_plan(self) -> dict[str, Any]:
        return await self._request("GET", "/api/plan")

    async def get_grid_stats(self) -> dict[str, Any]:
        return await self._request("GET", "/api/grid-stats")

    async def get_decision_history(self, limit: int) -> list[dict[str, Any]]:
        return await self._request("GET", "/api/history/decisions", params={"limit": limit})

    async def get_execution_history(self, limit: int) -> list[dict[str, Any]]:
        return await self._request("GET", "/api/history/executions", params={"limit": limit})

    async def get_shed_history(self, limit: int) -> list[dict[str, Any]]:
        return await self._request(
            "GET", "/api/history/shed-executions", params={"limit": limit}
        )

    async def get_telemetry_window(self, hours: int) -> list[dict[str, Any]]:
        return await self._request("GET", "/api/history/telemetry", params={"hours": hours})

    async def get_grid_events(self, days: int) -> list[dict[str, Any]]:
        return await self._request("GET", "/api/history/grid-events", params={"days": days})

    async def get_shed_snapshots(self) -> dict[str, Any]:
        return await self._request("GET", "/api/shed/snapshots")

    async def apply_override(
        self, ov: Override, *, confirm_kill_switch: bool
    ) -> dict[str, Any]:
        body = ov.model_dump(exclude_none=True)
        if ov.kill_switch:
            body["confirm"] = confirm_kill_switch
        return await self._request("POST", "/api/override", json=body)

    async def clear_override(self) -> dict[str, Any]:
        return await self._request("POST", "/api/override/clear")

    async def trigger_cycle(self) -> dict[str, Any]:
        return await self._request("POST", "/api/cycle")

    async def refresh_forecast(self) -> dict[str, Any]:
        return await self._request("POST", "/api/forecast/refresh")

    async def update_config(self, patch: dict) -> dict[str, Any]:
        return await self._request("PUT", "/api/config", json=patch)

    async def ask(self, question: str) -> dict[str, Any]:
        return await self._request("POST", "/api/assistant/ask", json={"question": question})
