from ..domain.errors import SiteNotAllowedError
from .ports import UniFiGateway


class UniFiUseCases:
    """Application use cases for read-only UniFi operations."""

    def __init__(self, gateway: UniFiGateway, allowed_site_ids: tuple[str, ...] = ()):
        self._gateway = gateway
        self._allowed_site_ids = frozenset(allowed_site_ids)

    def _validate_site(self, site_id: str | None) -> None:
        if site_id and self._allowed_site_ids and site_id not in self._allowed_site_ids:
            raise SiteNotAllowedError(site_id)

    async def list_sites(self):
        return await self._gateway.list_sites()

    async def list_devices(self, site_id: str | None = None):
        self._validate_site(site_id)
        return await self._gateway.list_devices(site_id)

    async def list_clients(self, site_id: str | None = None):
        self._validate_site(site_id)
        return await self._gateway.list_clients(site_id)

    async def get_health(self, site_id: str | None = None):
        self._validate_site(site_id)
        return await self._gateway.get_health(site_id)

    async def get_site(self, site_id: str):
        self._validate_site(site_id)
        return await self._gateway.get_site(site_id)
