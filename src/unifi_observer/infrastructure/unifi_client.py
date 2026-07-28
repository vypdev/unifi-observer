from __future__ import annotations

import ssl
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
        headers = {"Accept": "application/json", "User-Agent": "unifi-observer/0.1"}
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
        except httpx.ConnectError as exc:
            detail = str(exc).replace(self.settings.api_base_url, "<unifi-api>")[:240]
            raise UniFiAPIError(f"UniFi upstream connection failed: {detail}") from exc
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
            return await self._list_all_local_pages(site_id, "devices")
        params = {"siteId": site_id} if site_id else None
        return await self.get_json(self.path("devices"), params)

    async def list_clients(self, site_id: str | None = None):
        if self.settings.api_mode == "local":
            if not site_id:
                raise UniFiAPIError("site_id is required in local mode")
            return await self._list_all_local_pages(site_id, "clients")
        raise UniFiAPIError("list_clients is not supported by the site-manager API")

    async def _list_all_local_pages(self, site_id: str, resource: str) -> Any:
        """Fetch every page returned by the local Network Integration API."""
        page_size = 100
        offset = 0
        items: list[Any] = []
        first_payload: Any = None
        total_count: int | None = None

        while True:
            payload = await self.get_site_json(
                site_id,
                self.path(f"sites/{{site_id}}/{resource}"),
                params={"offset": offset, "limit": page_size},
            )
            if first_payload is None:
                first_payload = payload

            page = payload.get("data") if isinstance(payload, dict) else None
            if not isinstance(page, dict):
                return payload if not items else self._merge_page_payload(first_payload, items, len(items))

            reported_offset = page.get("offset")
            if isinstance(reported_offset, int) and reported_offset != offset:
                raise UniFiAPIError(f"UniFi pagination returned unexpected offset while listing {resource}")

            page_items = page.get("data")
            if not isinstance(page_items, list):
                return payload if not items else self._merge_page_payload(first_payload, items, len(items))

            items.extend(page_items)
            total_value = page.get("totalCount")
            if isinstance(total_value, int) and total_value >= 0:
                total_count = total_value

            if not page_items or (total_count is not None and len(items) >= total_count):
                break

            next_offset = offset + len(page_items)
            if next_offset <= offset:
                raise UniFiAPIError(f"UniFi pagination stalled while listing {resource}")
            offset = next_offset

        return self._merge_page_payload(first_payload, items, total_count or len(items))

    @staticmethod
    def _merge_page_payload(payload: Any, items: list[Any], total_count: int) -> Any:
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), dict):
            return payload
        page = payload["data"]
        return {
            **payload,
            "data": {
                **page,
                "offset": 0,
                "limit": len(items),
                "count": len(items),
                "totalCount": total_count,
                "data": items,
            },
        }

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

    def _tls_verify(self) -> bool | ssl.SSLContext:
        if self.settings.ca_cert_path:
            return ssl.create_default_context(cafile=self.settings.ca_cert_path)
        return self.settings.verify_tls

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
                verify=self._tls_verify(),
                transport=self._transport,
                trust_env=self.settings.api_mode != "local",
            )
        return self._http
