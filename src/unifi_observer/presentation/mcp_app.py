from __future__ import annotations

from collections.abc import Callable
from typing import Any

from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from ..application.ports import RuntimeInfo
from ..application.use_cases import UniFiUseCases
from ..domain.errors import SiteNotAllowedError, UniFiError


def create_mcp_app(
    settings: RuntimeInfo,
    use_cases: UniFiUseCases,
    lifespan: Callable[..., Any] | None = None,
) -> FastMCP:
    """Create the MCP/HTTP presentation adapter from injected application services."""
    app = FastMCP(
        "unifi-observer",
        instructions="Read-only UniFi network inventory and health. Write operations are disabled by default.",
        host=settings.host,
        port=settings.port,
        json_response=True,
        stateless_http=True,
        lifespan=lifespan,
    )

    @app.custom_route("/healthz", methods=["GET"])
    async def healthz(_: Request) -> JSONResponse:
        return JSONResponse({"status": "ok", "service": "unifi-observer", "version": "0.1.0"})

    @app.custom_route("/readyz", methods=["GET"])
    async def readyz(_: Request) -> JSONResponse:
        return JSONResponse({"status": "ready", "api_mode": settings.api_mode, "write_enabled": settings.enable_write})

    async def call(operation: Any) -> dict[str, Any]:
        try:
            return {"ok": True, "data": await operation()}
        except (UniFiError, SiteNotAllowedError) as exc:
            return {"ok": False, "error": str(exc), "status_code": getattr(exc, "status_code", None)}

    @app.tool()
    async def unifi_list_sites() -> dict[str, Any]:
        """List UniFi sites visible to the configured API credential."""
        return await call(use_cases.list_sites)

    @app.tool()
    async def unifi_list_devices(site_id: str | None = None) -> dict[str, Any]:
        """List all UniFi devices, optionally restricted to one site."""
        return await call(lambda: use_cases.list_devices(site_id or settings.site_id))

    @app.tool()
    async def unifi_list_clients(site_id: str | None = None) -> dict[str, Any]:
        """List all connected UniFi clients, optionally restricted to one site."""
        return await call(lambda: use_cases.list_clients(site_id or settings.site_id))

    @app.tool()
    async def unifi_get_health(site_id: str | None = None) -> dict[str, Any]:
        """Return UniFi health information for a site or the account."""
        return await call(lambda: use_cases.get_health(site_id or settings.site_id))

    @app.tool()
    async def unifi_get_site(site_id: str) -> dict[str, Any]:
        """Get details for one allowed UniFi site."""
        return await call(lambda: use_cases.get_site(site_id))

    return app
