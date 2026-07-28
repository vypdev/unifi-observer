"""Application use case for the short-lived UniFi web-console bootstrap."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from ..domain.errors import CertificateUploadError
from ..domain.unifi_web_api_models import (
    ActivateCertificateRequest,
    CreateApiKeyRequest,
    DeleteApiKeyRequest,
    DeleteCertificateRequest,
    ListApiKeysRequest,
    ListCertificatesRequest,
    LoginRequest,
    LoginSuccessResponse,
    MfaChallengeResponse,
    TwoFactorRequest,
    UploadCertificateRequest,
)
from .ports import UniFiWebConsolePort

TwoFactorProvider = Callable[[], Awaitable[str]]


@dataclass(frozen=True)
class BootstrapResult:
    """Verified bootstrap resources and their non-secret UniFi identifiers."""

    api_key: str
    api_key_id: str
    certificate_id: str


class UniFiConsoleBootstrap:
    """Orchestrate UniFi web-console bootstrap without transport concerns.

    The use case deliberately knows nothing about HTTP, cookies, headers, URLs,
    prompts, or the UniFi firmware. Those concerns belong to the injected port
    implementation and the outer CLI composition boundary.
    """

    def __init__(self, web_console: UniFiWebConsolePort):
        self._web_console = web_console

    async def run(
        self,
        *,
        username: str,
        password: str,
        certificate_name: str,
        certificate_pem: str,
        private_key_pem: str,
        request_two_factor: TwoFactorProvider,
        api_key_name: str,
    ) -> BootstrapResult:
        """Authenticate and replace the server-owned certificate and API key.

        Credentials and certificate material are passed through in memory and are
        never returned by this use case. The caller owns the lifetime of the
        injected web-console adapter and must close it in a ``finally`` block.
        """

        login_request = LoginRequest(username=username, password=password)
        login_response = await self._web_console.login(login_request)
        authenticated: LoginSuccessResponse
        if isinstance(login_response, MfaChallengeResponse):
            two_factor_token = await request_two_factor()
            if not two_factor_token:
                raise CertificateUploadError(
                    "a UniFi 2FA token is required for automatic certificate upload"
                )
            authenticated = await self._web_console.verify_2fa(
                TwoFactorRequest(
                    username=username,
                    password=password,
                    token=two_factor_token,
                )
            )
        else:
            authenticated = login_response

        user_id = authenticated.user.user_id
        if not user_id:
            raise CertificateUploadError("UniFi login returned no user ID for resource listing")

        existing_keys = tuple(
            key for key in (await self._web_console.list_api_keys(ListApiKeysRequest(user_id))).keys
            if key.name == api_key_name
        )
        existing_certificates = tuple(
            certificate
            for certificate in (await self._web_console.list_certificates(ListCertificatesRequest())).certificates
            if certificate.name == certificate_name
        )

        uploaded = await self._web_console.upload_certificate(
            UploadCertificateRequest(
                name=certificate_name,
                certificate_pem=certificate_pem,
                private_key_pem=private_key_pem,
            )
        )
        await self._web_console.activate_certificate(
            ActivateCertificateRequest(certificate_id=uploaded.certificate_id)
        )

        created = await self._web_console.create_api_key(
            CreateApiKeyRequest(
                user_id=user_id,
                name=api_key_name,
                description="UniFi Observer local integration key",
            )
        )
        if not created.key.full_api_key:
            raise CertificateUploadError("UniFi API key creation returned no key")
        if not created.key.key_id:
            raise CertificateUploadError("UniFi API key creation returned no key ID")

        for existing_key in existing_keys:
            if existing_key.key_id and existing_key.key_id != created.key.key_id:
                await self._web_console.delete_api_key(DeleteApiKeyRequest(existing_key.key_id))
        for existing_certificate in existing_certificates:
            if existing_certificate.certificate_id and existing_certificate.certificate_id != uploaded.certificate_id:
                await self._web_console.delete_certificate(
                    DeleteCertificateRequest(existing_certificate.certificate_id)
                )
        return BootstrapResult(created.key.full_api_key, created.key.key_id, uploaded.certificate_id)
