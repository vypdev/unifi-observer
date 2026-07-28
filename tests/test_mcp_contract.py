from types import SimpleNamespace

import pytest

from unifi_observer.application.use_cases import UniFiUseCases
from unifi_observer.presentation.mcp_app import create_mcp_app


class ContractGateway:
    async def list_sites(self):
        return {"data": [{"id": "site-1"}]}

    async def list_devices(self, site_id=None):
        return {"site_id": site_id}

    async def list_clients(self, site_id=None):
        return {"site_id": site_id}

    async def get_health(self, site_id=None):
        return {"site_id": site_id}

    async def get_site(self, site_id):
        return {"id": site_id}


def make_app():
    settings = SimpleNamespace(
        host="127.0.0.1",
        port=8000,
        api_mode="site-manager",
        enable_write=False,
        site_id=None,
    )
    return create_mcp_app(settings, UniFiUseCases(ContractGateway()))


@pytest.mark.asyncio
async def test_mcp_contract_exposes_all_read_only_tools():
    app = make_app()
    tools = await app.list_tools()

    assert [tool.name for tool in tools] == [
        "unifi_list_sites",
        "unifi_list_devices",
        "unifi_list_clients",
        "unifi_get_health",
        "unifi_get_site",
    ]
    assert {route.path for route in app._custom_starlette_routes} == {"/healthz", "/readyz"}


@pytest.mark.asyncio
async def test_mcp_contract_invokes_tool_through_application_layer():
    app = make_app()
    result = await app.call_tool("unifi_list_sites", {})

    assert result[1] == {"ok": True, "data": {"data": [{"id": "site-1"}]}}
