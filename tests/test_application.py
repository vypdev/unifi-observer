import pytest

from unifi_observer.application.ports import UniFiGateway
from unifi_observer.application.use_cases import UniFiUseCases


class FakeGateway(UniFiGateway):
    async def list_sites(self):
        return {"data": [{"id": "site-1"}]}

    async def list_devices(self, site_id=None):
        return {"data": [{"id": "device-1", "site_id": site_id}]}

    async def list_clients(self, site_id=None):
        return {"data": [{"id": "client-1", "site_id": site_id}]}

    async def get_health(self, site_id=None):
        return {"data": [{"status": "ok", "site_id": site_id}]}

    async def get_site(self, site_id):
        return {"data": {"id": site_id}}


@pytest.mark.asyncio
async def test_use_cases_delegate_read_operations_to_gateway():
    use_cases = UniFiUseCases(FakeGateway())

    assert await use_cases.list_sites() == {"data": [{"id": "site-1"}]}
    assert await use_cases.list_devices("site-1") == {
        "data": [{"id": "device-1", "site_id": "site-1"}]
    }
    assert await use_cases.list_clients("site-1") == {
        "data": [{"id": "client-1", "site_id": "site-1"}]
    }
    assert await use_cases.get_health("site-1") == {
        "data": [{"status": "ok", "site_id": "site-1"}]
    }
    assert await use_cases.get_site("site-1") == {"data": {"id": "site-1"}}


@pytest.mark.asyncio
async def test_use_cases_reject_site_outside_allowlist():
    use_cases = UniFiUseCases(FakeGateway(), allowed_site_ids=("site-allowed",))

    with pytest.raises(ValueError, match="not allowed"):
        await use_cases.get_site("site-blocked")
