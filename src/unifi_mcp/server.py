from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from .client import UniFiAPIError, UniFiClient
from .config import Settings

settings = Settings.from_env()
settings.validate()
client = UniFiClient(settings)
mcp = FastMCP(
    "unifi-mcp-coolify",
    instructions="Read-only UniFi network inventory and health. Write operations are disabled by default.",
    host=settings.host,
    port=settings.port,
    json_response=True,
    stateless_http=True,
)


@mcp.custom_route("/healthz", methods=["GET"])
async def healthz(_: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "unifi-mcp-coolify", "version": "0.1.0"})


@mcp.custom_route("/readyz", methods=["GET"])
async def readyz(_: Request) -> JSONResponse:
    return JSONResponse({"status": "ready", "api_mode": settings.api_mode, "write_enabled": settings.enable_write})


async def _call(operation: Any) -> dict[str, Any]:
    try:
        result = await operation()
        return {"ok": True, "data": result}
    except UniFiAPIError as exc:
        return {"ok": False, "error": str(exc), "status_code": exc.status_code}


@mcp.tool()
async def unifi_list_sites() -> dict[str, Any]:
    """List UniFi sites visible to the configured API credential."""
    return await _call(lambda: client.get_json(client.path("sites")))


@mcp.tool()
async def unifi_list_devices(site_id: str | None = None) -> dict[str, Any]:
    """List UniFi devices, optionally restricted to one site."""
    selected = site_id or settings.site_id
    if settings.api_mode == "network-integration":
        if not selected:
            return {"ok": False, "error": "site_id is required in network-integration mode"}
        return await _call(lambda: client.get_site_json(selected, client.path("sites/{site_id}/devices")))
    params = {"siteId": selected} if selected else None
    if selected and settings.allowed_site_ids and selected not in settings.allowed_site_ids:
        return {"ok": False, "error": f"site '{selected}' is not allowed"}
    return await _call(lambda: client.get_json(client.path("devices"), params))


@mcp.tool()
async def unifi_list_clients(site_id: str | None = None) -> dict[str, Any]:
    """List connected UniFi clients, optionally restricted to one site."""
    selected = site_id or settings.site_id
    if settings.api_mode == "network-integration":
        if not selected:
            return {"ok": False, "error": "site_id is required in network-integration mode"}
        return await _call(lambda: client.get_site_json(selected, client.path("sites/{site_id}/clients")))
    params = {"siteId": selected} if selected else None
    if selected and settings.allowed_site_ids and selected not in settings.allowed_site_ids:
        return {"ok": False, "error": f"site '{selected}' is not allowed"}
    return await _call(lambda: client.get_json(client.path("clients"), params))


@mcp.tool()
async def unifi_get_health(site_id: str | None = None) -> dict[str, Any]:
    """Return UniFi health information for a site or the account."""
    selected = site_id or settings.site_id
    if settings.api_mode == "network-integration":
        if not selected:
            return {"ok": False, "error": "site_id is required in network-integration mode"}
        return await _call(lambda: client.get_site_json(selected, client.path("sites/{site_id}/health")))
    params = {"siteId": selected} if selected else None
    if selected and settings.allowed_site_ids and selected not in settings.allowed_site_ids:
        return {"ok": False, "error": f"site '{selected}' is not allowed"}
    return await _call(lambda: client.get_json(client.path("health"), params))


@mcp.tool()
async def unifi_get_site(site_id: str) -> dict[str, Any]:
    """Get details for one allowed UniFi site."""
    return await _call(lambda: client.get_site_json(site_id, client.path("sites/{site_id}")))


def main() -> None:
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
