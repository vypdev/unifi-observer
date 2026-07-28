class SiteNotAllowedError(ValueError):
    """Raised when a site is outside the configured read allowlist."""

    def __init__(self, site_id: str):
        super().__init__(f"site '{site_id}' is not allowed")
        self.site_id = site_id


class UniFiError(RuntimeError):
    """Stable application-facing error for upstream or adapter failures."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class CertificateUploadError(UniFiError):
    """Raised when the UniFi OS bootstrap workflow cannot complete."""


class TwoFactorRequiredError(CertificateUploadError):
    """Raised when UniFi requires a one-time authentication token."""

    def __init__(self, message: str, status_code: int | None = None, *, sso: bool = False):
        super().__init__(message, status_code)
        self.sso = sso
