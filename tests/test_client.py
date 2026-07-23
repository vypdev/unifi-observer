import httpx
import pytest

from unifi_mcp.client import UniFiAPIError, UniFiClient
from unifi_mcp.config import Settings


def make_settings(**overrides):
    values = {
        "api_mode": "site-manager",
        "api_base_url": "https://api.ui.com",
        "api_key": "[REDACTED]",
        "site_id": "site-1",
        "allowed_site_ids": (),
        "verify_tls": True,
        "timeout_seconds": 5.0,
        "enable_write": False,
    }
    values.update(overrides)
    return Settings(**values)


@pytest.mark.asyncio
async def test_get_json_uses_x_api_key_and_returns_payload():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["api_key"] = request.headers.get("x-api-key")
        return httpx.Response(200, json={"data": [{"id": "site-1"}]})

    client = UniFiClient(make_settings(), transport=httpx.MockTransport(handler))
    result = await client.get_json("/v1/sites")

    assert result == {"data": [{"id": "site-1"}]}
    assert seen == {"path": "/v1/sites", "api_key": "[REDACTED]"}
    await client.aclose()


@pytest.mark.asyncio
async def test_site_allowlist_blocks_unapproved_site_before_request():
    def handler(_: httpx.Request) -> httpx.Response:
        raise AssertionError("network request should not be made")

    client = UniFiClient(
        make_settings(allowed_site_ids=("site-allowed",)),
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(UniFiAPIError, match="not allowed"):
        await client.get_site_json("site-blocked", "/v1/sites/{site_id}")
    await client.aclose()


@pytest.mark.asyncio
async def test_http_errors_are_normalized_without_response_dump():
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="upstream internal details")

    client = UniFiClient(make_settings(), transport=httpx.MockTransport(handler))

    with pytest.raises(UniFiAPIError) as error:
        await client.get_json("/v1/sites")
    assert error.value.status_code == 503
    assert "upstream internal details" not in str(error.value)
    await client.aclose()
