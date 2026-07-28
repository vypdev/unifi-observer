from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx

from ..application.ports import UniFiGateway
from ..domain.errors import UniFiError
from .config import Settings

UniFiAPIError = UniFiError


class UniFiClient(UniFiGateway):
    """HTTP adapter for the supported UniFi upstream APIs."""

    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        settings.validate()
        self.settings = settings
        headers = {"Accept": "application/json", "User-Agent": "unifi-mcp-coolify/0.1"}
        if settings.api_key:
            headers["X-API-Key"] = settings.api_key
        self._headers = headers
        self._transport = transport
        self._http: httpx.AsyncClient | None = None
        self._ensure_http()

    async def aclose(self) -> None:
        if self._http is not None:
            await self._http.aclose()

    async def get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        try:
            response = await self._ensure_http().get(path, params=params)
        except httpx.HTTPError as exc:
            raise UniFiAPIError(f"UniFi upstream unavailable: {type(exc).__name__}") from exc
        if response.status_code >= 400:
            raise UniFiAPIError(f"UniFi upstream returned HTTP {response.status_code}", response.status_code)
        try:
            return response.json()
        except ValueError as exc:
            raise UniFiAPIError("UniFi upstream returned invalid JSON", response.status_code) from exc

    async def list_sites(self):
        return await self.get_json(self.path("sites"))

    async def list_devices(self, site_id: str | None = None):
        if self.settings.api_mode == "local":
            if not site_id:
                raise UniFiAPIError("site_id is required in local mode")
            return await self.get_site_json(site_id, self.path("sites/{site_id}/devices"))
        params = {"siteId": site_id} if site_id else None
        return await self.get_json(self.path("devices"), params)

    async def list_clients(self, site_id: str | None = None):
        if self.settings.api_mode == "local":
            if not site_id:
                raise UniFiAPIError("site_id is required in local mode")
            return await self.get_site_json(site_id, self.path("sites/{site_id}/clients"))
        raise UniFiAPIError("list_clients is not supported by the site-manager API")

    async def get_health(self, site_id: str | None = None):
        if self.settings.api_mode == "local":
            if not site_id:
                raise UniFiAPIError("site_id is required in local mode")
            return await self.get_site_json(site_id, self.path("sites/{site_id}/health"))
        raise UniFiAPIError("get_health is not supported by the site-manager API")

    async def get_site(self, site_id: str):
        self._check_site(site_id)
        if self.settings.api_mode == "local":
            return await self.get_site_json(site_id, self.path("sites/{site_id}"))
        payload = await self.list_sites()
        sites = payload.get("data", []) if isinstance(payload, dict) else []
        for site in sites:
            if isinstance(site, dict) and site.get("siteId") == site_id:
                return site
        raise UniFiAPIError(f"site '{site_id}' was not found", 404)

    def _check_site(self, site_id: str) -> None:
        if self.settings.allowed_site_ids and site_id not in self.settings.allowed_site_ids:
            raise UniFiAPIError(f"site '{site_id}' is not allowed")

    async def get_site_json(self, site_id: str, path_template: str, params: dict[str, Any] | None = None):
        self._check_site(site_id)
        path = path_template.format(site_id=quote(site_id, safe=""))
        return await self.get_json(path, params)

    def path(self, resource: str) -> str:
        if self.settings.api_mode == "local":
            return f"/proxy/network/integration/v1/{resource.lstrip('/')}"
        return f"/v1/{resource.lstrip('/')}"

    def _ensure_http(self) -> httpx.AsyncClient:
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(
                base_url=self.settings.api_base_url,
                headers=self._headers,
                timeout=self.settings.timeout_seconds,
                verify=self.settings.verify_tls,
                transport=self._transport,
            )
        return self._http
