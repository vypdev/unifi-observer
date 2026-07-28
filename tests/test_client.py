import httpx
import pytest

from unifi_observer.client import UniFiAPIError, UniFiClient
from unifi_observer.config import Settings


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


def test_network_integration_alias_is_normalized_to_local():
    assert make_settings(api_mode="network-integration").api_mode == "local"


def test_local_mode_uses_network_integration_paths():
    client = UniFiClient(make_settings(api_mode="local"), transport=httpx.MockTransport(lambda _: httpx.Response(200)))
    assert client.path("sites/site-1/devices") == "/proxy/network/integration/v1/sites/site-1/devices"


def test_invalid_mode_is_rejected():
    with pytest.raises(ValueError, match="site-manager or local"):
        make_settings(api_mode="unsupported")


def test_custom_ca_certificate_must_exist(tmp_path):
    with pytest.raises(ValueError, match="UNIFI_CA_CERT_PATH"):
        make_settings(ca_cert_path=str(tmp_path / "missing-ca.crt"))


def test_custom_ca_certificate_is_accepted(tmp_path):
    ca_path = tmp_path / "ca.crt"
    ca_path.write_text("test CA", encoding="utf-8")
    assert make_settings(ca_cert_path=str(ca_path)).ca_cert_path == str(ca_path)


def test_client_passes_custom_ca_to_httpx(tmp_path, monkeypatch):
    ca_path = tmp_path / "ca.crt"
    ca_path.write_text("test CA", encoding="utf-8")
    captured = {}

    class FakeAsyncClient:
        is_closed = False

        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    UniFiClient(make_settings(ca_cert_path=str(ca_path)))

    assert captured["verify"] == str(ca_path)


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


@pytest.mark.asyncio
async def test_site_manager_rejects_operations_not_in_official_contract():
    client = UniFiClient(make_settings(), transport=httpx.MockTransport(lambda _: httpx.Response(500)))

    with pytest.raises(UniFiAPIError, match="not supported"):
        await client.list_clients()
    with pytest.raises(UniFiAPIError, match="not supported"):
        await client.get_health()
    await client.aclose()


@pytest.mark.asyncio
async def test_site_manager_get_site_filters_the_list_sites_response():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/sites"
        return httpx.Response(200, json={"data": [{"siteId": "site-1", "meta": {"name": "Default"}}]})

    client = UniFiClient(make_settings(), transport=httpx.MockTransport(handler))
    assert await client.get_site("site-1") == {"siteId": "site-1", "meta": {"name": "Default"}}
    await client.aclose()
