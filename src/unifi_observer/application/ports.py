from typing import Any, Protocol

from ..domain.unifi_web_api_models import (
    ActivateCertificateRequest,
    ActivateCertificateResponse,
    CreateApiKeyRequest,
    CreateApiKeyResponse,
    DeleteApiKeyRequest,
    DeleteCertificateRequest,
    DeleteResourceResponse,
    ListApiKeysRequest,
    ListApiKeysResponse,
    ListCertificatesRequest,
    ListCertificatesResponse,
    LoginRequest,
    LoginResponse,
    LoginSuccessResponse,
    TwoFactorRequest,
    UploadCertificateRequest,
    UploadCertificateResponse,
)


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
    """Typed application boundary for the short-lived UniFi OS web API."""

    async def login(self, request: LoginRequest) -> LoginResponse: ...

    async def verify_2fa(self, request: TwoFactorRequest) -> LoginSuccessResponse: ...

    async def upload_certificate(self, request: UploadCertificateRequest) -> UploadCertificateResponse: ...

    async def activate_certificate(self, request: ActivateCertificateRequest) -> ActivateCertificateResponse: ...

    async def create_api_key(self, request: CreateApiKeyRequest) -> CreateApiKeyResponse: ...

    async def delete_api_key(self, request: DeleteApiKeyRequest) -> DeleteResourceResponse: ...

    async def delete_certificate(self, request: DeleteCertificateRequest) -> DeleteResourceResponse: ...

    async def list_api_keys(self, request: ListApiKeysRequest) -> ListApiKeysResponse: ...

    async def list_certificates(self, request: ListCertificatesRequest) -> ListCertificatesResponse: ...

    async def aclose(self) -> None: ...


class UniFiGateway(Protocol):
    async def list_sites(self) -> Any: ...

    async def list_devices(self, site_id: str | None = None) -> Any: ...

    async def list_clients(self, site_id: str | None = None) -> Any: ...

    async def get_health(self, site_id: str | None = None) -> Any: ...

    async def get_site(self, site_id: str) -> Any: ...
