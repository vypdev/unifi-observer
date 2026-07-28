"""Backward-compatible imports for the infrastructure adapter."""

from .domain.errors import UniFiError
from .infrastructure.unifi_client import UniFiClient

UniFiAPIError = UniFiError

__all__ = ["UniFiAPIError", "UniFiClient"]
