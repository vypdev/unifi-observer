"""Application use case for the short-lived UniFi web-console bootstrap."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from ..domain.errors import CertificateUploadError, TwoFactorRequiredError
from .ports import UniFiWebConsolePort

TwoFactorProvider = Callable[[], Awaitable[str]]


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
        generate_api_key: bool,
    ) -> str | None:
        """Authenticate, upload/activate certificates, and optionally create a key.

        Credentials and certificate material are passed through in memory and are
        never returned by this use case. The caller owns the lifetime of the
        injected web-console adapter and must close it in a ``finally`` block.
        """

        try:
            await self._web_console.authenticate(username, password)
        except TwoFactorRequiredError:
            two_factor_token = await request_two_factor()
            if not two_factor_token:
                raise CertificateUploadError(
                    "a UniFi 2FA token is required for automatic certificate upload"
                )
            await self._web_console.authenticate(
                username,
                password,
                two_factor_token,
            )

        await self._web_console.upload_and_activate(
            certificate_name=certificate_name,
            certificate_pem=certificate_pem,
            private_key_pem=private_key_pem,
        )

        if not generate_api_key:
            return None
        return await self._web_console.create_api_key(
            name="unifi-observer",
            description="UniFi Observer local integration key",
        )
