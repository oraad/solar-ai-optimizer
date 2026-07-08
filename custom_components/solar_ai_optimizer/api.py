"""HTTP client for the Solar AI Optimizer API."""

from __future__ import annotations

from typing import Any

from aiohttp import ClientError, ClientResponseError, ClientSession


class SolarAiClient:
    """Async HTTP client talking to a Solar AI Optimizer instance."""

    def __init__(
        self,
        host: str,
        access_token: str,
        verify_ssl: bool,
        session: ClientSession,
    ) -> None:
        self._host = host.rstrip("/")
        self._access_token = access_token
        self._verify_ssl = verify_ssl
        self._session = session

    @property
    def host(self) -> str:
        """Return the base host URL without a trailing slash."""
        return self._host

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Accept": "application/json"}
        if self._access_token:
            headers["Authorization"] = f"Bearer {self._access_token}"
        return headers

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        auth: bool = True,
    ) -> Any:
        url = f"{self._host}{path}"
        headers = self._headers() if auth else {"Accept": "application/json"}
        try:
            async with self._session.request(
                method,
                url,
                headers=headers,
                json=json,
                params=params,
                ssl=self._verify_ssl,
            ) as response:
                response.raise_for_status()
                if response.status == 204:
                    return None
                return await response.json(content_type=None)
        except ClientResponseError:
            raise
        except ClientError:
            raise

    async def get_health(self) -> dict[str, Any]:
        """GET /api/health (no auth required on the Solar side)."""
        return await self._request("GET", "/api/health", auth=False)

    async def get_update_info(self, refresh: bool = False) -> dict[str, Any]:
        """GET /api/system/update."""
        params = {"refresh": "true"} if refresh else None
        return await self._request("GET", "/api/system/update", params=params)

    async def apply_update(self, version: str | None = None) -> dict[str, Any]:
        """POST /api/system/update."""
        body: dict[str, Any] = {}
        if version is not None:
            body["version"] = version
        return await self._request("POST", "/api/system/update", json=body or None)

    async def get_config(self) -> dict[str, Any]:
        """GET /api/config."""
        return await self._request("GET", "/api/config")

    async def redeem_pair(
        self,
        code: str,
        client_name: str = "Home Assistant",
    ) -> dict[str, Any]:
        """POST /api/pair/redeem."""
        return await self._request(
            "POST",
            "/api/pair/redeem",
            json={"code": code, "client_name": client_name},
            auth=False,
        )
