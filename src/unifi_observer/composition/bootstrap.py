from __future__ import annotations

from contextlib import asynccontextmanager

from ..application.use_cases import UniFiUseCases
from ..infrastructure.config import Settings
from ..infrastructure.unifi_client import UniFiClient
from ..presentation.mcp_app import create_mcp_app


def create_app(settings: Settings | None = None):
    """Compose the default production application."""
    resolved_settings = settings or Settings.from_env()
    resolved_settings.validate()
    client = UniFiClient(resolved_settings)
    use_cases = UniFiUseCases(client, resolved_settings.allowed_site_ids)

    @asynccontextmanager
    async def lifespan(_):
        try:
            yield
        finally:
            await client.aclose()

    return create_mcp_app(resolved_settings, use_cases, lifespan)
