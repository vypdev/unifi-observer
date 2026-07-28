import pytest

from unifi_observer.application.bootstrap import UniFiConsoleBootstrap
from unifi_observer.domain.unifi_web_api_models import (
    ActivateCertificateResponse,
    ApiKeyMetadata,
    CertificateMetadata,
    CreateApiKeyResponse,
    DeleteResourceResponse,
    ListApiKeysResponse,
    ListCertificatesResponse,
    LoginSuccessResponse,
    MfaChallengeResponse,
    SessionCredentials,
    UniFiUserProfile,
    UploadCertificateResponse,
)


class FakeWebConsole:
    def __init__(self, existing=False):
        self.calls = []
        self.existing = existing
        self.success = LoginSuccessResponse(
            200,
            UniFiUserProfile("user-1", None, "admin", None, None, None, None, None, None, None, None),
            SessionCredentials(csrf_token="csrf"),
        )

    async def login(self, request):
        self.calls.append(("login", request))
        return MfaChallengeResponse(499, "MFA_AUTH_REQUIRED", "MFA required", "2fa")

    async def verify_2fa(self, request):
        self.calls.append(("verify_2fa", request))
        return self.success

    async def upload_certificate(self, request):
        self.calls.append(("upload_certificate", request))
        return UploadCertificateResponse(200, "certificate-1")

    async def list_api_keys(self, request):
        self.calls.append(("list_api_keys", request))
        keys = (ApiKeyMetadata("old-key", "unifi-observer-ai-core", "old", None, None),) if self.existing else ()
        return ListApiKeysResponse(200, keys)

    async def list_certificates(self, request):
        self.calls.append(("list_certificates", request))
        certificates = (
            CertificateMetadata(
                certificate_id="old-certificate",
                name="unifi.local-ai-core",
                version=3,
                serial_number=None,
                fingerprint=None,
                subject={},
                issuer={},
                subject_alt_name={},
                valid_from=None,
                valid_to=None,
                created_at=None,
                updated_at=None,
                source="uploaded",
                acme_renew_error=None,
                active=True,
            ),
        ) if self.existing else ()
        return ListCertificatesResponse(200, certificates)

    async def activate_certificate(self, request):
        self.calls.append(("activate_certificate", request))
        return ActivateCertificateResponse(200, True)

    async def create_api_key(self, request):
        self.calls.append(("create_api_key", request))
        return CreateApiKeyResponse(
            200,
            ApiKeyMetadata(
                "key-1",
                request.name,
                request.description,
                None,
                None,
                full_api_key="generated-key",
            ),
        )

    async def delete_api_key(self, request):
        self.calls.append(("delete_api_key", request))
        return DeleteResourceResponse(200, True)

    async def delete_certificate(self, request):
        self.calls.append(("delete_certificate", request))
        return DeleteResourceResponse(204, True)

    async def aclose(self):
        pass


@pytest.mark.asyncio
async def test_bootstrap_orchestrates_mfa_upload_activation_and_api_key():
    gateway = FakeWebConsole()
    requested = []

    async def request_two_factor():
        requested.append(True)
        return "123456"

    result = await UniFiConsoleBootstrap(gateway).run(
        username="admin",
        password="password",
        certificate_name="unifi.local",
        certificate_pem="CERTIFICATE",
        private_key_pem="PRIVATE-KEY",
        request_two_factor=request_two_factor,
        api_key_name="unifi-observer-ai-core",
    )

    assert result.api_key == "generated-key"
    assert result.api_key_id == "key-1"
    assert result.certificate_id == "certificate-1"
    assert requested == [True]
    assert [call[0] for call in gateway.calls] == [
        "login",
        "verify_2fa",
        "list_api_keys",
        "list_certificates",
        "upload_certificate",
        "activate_certificate",
        "create_api_key",
    ]


@pytest.mark.asyncio
async def test_bootstrap_recreates_server_key_when_configured():
    gateway = FakeWebConsole()

    async def request_two_factor():
        return "123456"

    result = await UniFiConsoleBootstrap(gateway).run(
        username="admin",
        password="password",
        certificate_name="unifi.local",
        certificate_pem="CERTIFICATE",
        private_key_pem="PRIVATE-KEY",
        request_two_factor=request_two_factor,
        api_key_name="unifi-observer",
    )

    assert result.api_key == "generated-key"
    assert [call[0] for call in gateway.calls] == [
        "login",
        "verify_2fa",
        "list_api_keys",
        "list_certificates",
        "upload_certificate",
        "activate_certificate",
        "create_api_key",
    ]


@pytest.mark.asyncio
async def test_bootstrap_replaces_only_exact_server_resources_after_new_resources_exist():
    gateway = FakeWebConsole(existing=True)

    async def request_two_factor():
        return "123456"

    await UniFiConsoleBootstrap(gateway).run(
        username="admin",
        password="password",
        certificate_name="unifi.local-ai-core",
        certificate_pem="CERTIFICATE",
        private_key_pem="PRIVATE-KEY",
        request_two_factor=request_two_factor,
        api_key_name="unifi-observer-ai-core",
    )

    assert [call[0] for call in gateway.calls] == [
        "login",
        "verify_2fa",
        "list_api_keys",
        "list_certificates",
        "upload_certificate",
        "activate_certificate",
        "create_api_key",
        "delete_api_key",
        "delete_certificate",
    ]
    assert gateway.calls[-2][1].key_id == "old-key"
    assert gateway.calls[-1][1].certificate_id == "old-certificate"
