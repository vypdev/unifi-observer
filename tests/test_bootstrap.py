import pytest

from unifi_observer.application.bootstrap import UniFiConsoleBootstrap
from unifi_observer.domain.unifi_web_api_models import (
    ActivateCertificateResponse,
    ApiKeyMetadata,
    CreateApiKeyResponse,
    LoginSuccessResponse,
    MfaChallengeResponse,
    SessionCredentials,
    UniFiUserProfile,
    UploadCertificateResponse,
)


class FakeWebConsole:
    def __init__(self):
        self.calls = []
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
        generate_api_key=True,
    )

    assert result == "generated-key"
    assert requested == [True]
    assert [call[0] for call in gateway.calls] == [
        "login",
        "verify_2fa",
        "upload_certificate",
        "activate_certificate",
        "create_api_key",
    ]


@pytest.mark.asyncio
async def test_bootstrap_does_not_create_key_when_existing_key_is_configured():
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
        generate_api_key=False,
    )

    assert result is None
    assert [call[0] for call in gateway.calls] == [
        "login",
        "verify_2fa",
        "upload_certificate",
        "activate_certificate",
    ]
