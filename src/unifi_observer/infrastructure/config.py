from __future__ import annotations

import os
from dataclasses import dataclass

MODE_ALIASES = {
    "site-manager": "site-manager",
    "local": "local",
    "network-integration": "local",
}


@dataclass(frozen=True)
class Settings:
    api_mode: str
    api_base_url: str
    api_key: str | None
    site_id: str | None
    allowed_site_ids: tuple[str, ...]
    verify_tls: bool
    timeout_seconds: float
    enable_write: bool
    host: str = "0.0.0.0"
    port: int = 8000

    def __post_init__(self) -> None:
        try:
            canonical_mode = MODE_ALIASES[self.api_mode.strip().lower()]
        except KeyError as exc:
            raise ValueError("UNIFI_API_MODE must be site-manager or local") from exc
        object.__setattr__(self, "api_mode", canonical_mode)

    @classmethod
    def from_env(cls) -> Settings:
        allowed = tuple(x.strip() for x in os.getenv("UNIFI_ALLOWED_SITE_IDS", "").split(",") if x.strip())
        return cls(
            api_mode=os.getenv("UNIFI_API_MODE", "site-manager"),
            api_base_url=os.getenv("UNIFI_API_BASE_URL", "https://api.ui.com").rstrip("/"),
            api_key=os.getenv("UNIFI_API_KEY") or None,
            site_id=os.getenv("UNIFI_SITE_ID") or None,
            allowed_site_ids=allowed,
            verify_tls=os.getenv("UNIFI_VERIFY_TLS", "true").lower() not in {"0", "false", "no"},
            timeout_seconds=float(os.getenv("UNIFI_TIMEOUT_SECONDS", "15")),
            enable_write=os.getenv("UNIFI_ENABLE_WRITE", "false").lower() in {"1", "true", "yes"},
            host=os.getenv("MCP_HOST", "0.0.0.0"),
            port=int(os.getenv("MCP_PORT", "8000")),
        )

    def validate(self) -> None:
        if self.api_mode not in {"site-manager", "local"}:
            raise ValueError("UNIFI_API_MODE must be site-manager or local")
        if not self.api_base_url.startswith(("https://", "http://")):
            raise ValueError("UNIFI_API_BASE_URL must be an HTTP(S) URL")
        if self.timeout_seconds <= 0:
            raise ValueError("UNIFI_TIMEOUT_SECONDS must be positive")
        if self.port < 1 or self.port > 65535:
            raise ValueError("MCP_PORT must be a valid TCP port")
