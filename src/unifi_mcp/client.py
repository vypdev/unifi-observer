from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx

from .config import Settings


class UniFiAPIError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class UniFiClient:
    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        settings.validate()
        self.settings = settings
        headers = {"Accept": "application/json", "User-Agent": "unifi-mcp-coolify/0.1"}
        if settings.api_key:
            headers["X-API-Key"] = settings.api_key
        self._http = httpx.AsyncClient(
            base_url=settings.api_base_url,
            headers=headers,
            timeout=settings.timeout_seconds,
            verify=settings.verify_tls,
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        try:
            response = await self._http.get(path, params=params)
        except httpx.HTTPError as exc:
            raise UniFiAPIError(f"UniFi upstream unavailable: {type(exc).__name__}") from exc
        if response.status_code >= 400:
            raise UniFiAPIError(f"UniFi upstream returned HTTP {response.status_code}", response.status_code)
        try:
            return response.json()
        except ValueError as exc:
            raise UniFiAPIError("UniFi upstream returned invalid JSON", response.status_code) from exc

    def _check_site(self, site_id: str) -> None:
        if self.settings.allowed_site_ids and site_id not in self.settings.allowed_site_ids:
            raise UniFiAPIError(f"site '{site_id}' is not allowed")

    async def get_site_json(self, site_id: str, path_template: str, params: dict[str, Any] | None = None) -> Any:
        self._check_site(site_id)
        path = path_template.format(site_id=quote(site_id, safe=""))
        return await self.get_json(path, params)

    def path(self, resource: str) -> str:
        if self.settings.api_mode == "network-integration":
            return f"/proxy/network/integration/v1/{resource.lstrip('/')}"
        return f"/v1/{resource.lstrip('/')}"
