import pytest

from unifi_observer.application.bootstrap import UniFiConsoleBootstrap
from unifi_observer.domain.errors import TwoFactorRequiredError


class FakeWebConsole:
    def __init__(self):
        self.calls = []

    async def authenticate(self, username, password, two_factor_token=None):
        self.calls.append(("authenticate", username, password, two_factor_token))
        if two_factor_token is None:
            raise TwoFactorRequiredError("MFA required", 499, sso=True)

    async def upload_and_activate(self, **kwargs):
        self.calls.append(("upload", kwargs["certificate_name"]))

    async def create_api_key(self, name, description):
        self.calls.append(("create_api_key", name, description))
        return "generated-key"

    async def aclose(self):
        self.calls.append(("close",))


@pytest.mark.asyncio
async def test_bootstrap_orchestrates_mfa_upload_and_api_key():
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
    assert gateway.calls == [
        ("authenticate", "admin", "password", None),
        ("authenticate", "admin", "password", "123456"),
        ("upload", "unifi.local"),
        ("create_api_key", "unifi-observer", "UniFi Observer local integration key"),
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
    assert gateway.calls[-1][0] == "upload"
