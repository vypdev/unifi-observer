from typing import Any, Protocol


class RuntimeInfo(Protocol):
    @property
    def host(self) -> str: ...

    @property
    def port(self) -> int: ...

    @property
    def api_mode(self) -> str: ...

    @property
    def enable_write(self) -> bool: ...

    @property
    def site_id(self) -> str | None: ...


class UniFiWebConsolePort(Protocol):
    """Application port for the short-lived UniFi OS bootstrap session."""

    async def authenticate(
        self,
        username: str,
        password: str,
        two_factor_token: str | None = None,
    ) -> None: ...

    async def upload_and_activate(
        self,
        *,
        certificate_name: str,
        certificate_pem: str,
        private_key_pem: str,
    ) -> None: ...

    async def create_api_key(self, name: str, description: str) -> str: ...

    async def aclose(self) -> None: ...


class UniFiGateway(Protocol):
    async def list_sites(self) -> Any: ...

    async def list_devices(self, site_id: str | None = None) -> Any: ...

    async def list_clients(self, site_id: str | None = None) -> Any: ...

    async def get_health(self, site_id: str | None = None) -> Any: ...

    async def get_site(self, site_id: str) -> Any: ...
