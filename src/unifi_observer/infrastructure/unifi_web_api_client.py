"""Typed client for the UniFi OS web-console bootstrap API."""

from __future__ import annotations

import base64
import json
from typing import Any

import httpx

from ..domain.errors import CertificateUploadError
from ..domain.unifi_web_api_models import (
    ActivateCertificateRequest,
    ActivateCertificateResponse,
    CreateApiKeyRequest,
    CreateApiKeyResponse,
    LoginRequest,
    LoginResponse,
    LoginSuccessResponse,
    MfaChallengeResponse,
    SessionCredentials,
    TwoFactorRequest,
    UploadCertificateRequest,
    UploadCertificateResponse,
    parse_api_key_response,
    parse_mfa_challenge,
    parse_payload,
    parse_user_profile,
)


class UniFiWebApiClient:
    """Typed, short-lived client for the observed UniFi OS web API contract."""

    def __init__(
        self,
        base_url: str,
        timeout_seconds: float = 15.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not base_url.startswith("https://"):
            raise ValueError("UniFi web API requires an HTTPS Console URL")
        self._http = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout_seconds,
            verify=False,
            transport=transport,
        )
        self._session: SessionCredentials | None = None
        self._user_id: str | None = None

    async def aclose(self) -> None:
        await self._http.aclose()
        self._session = None
        self._user_id = None

    async def login(self, request: LoginRequest) -> LoginResponse:
        """Perform the initial login and return either success or an MFA challenge."""
        response = await self._post_json("/api/auth/login", request.to_payload(), "AUTHENTICATION_FAILED")
        payload = parse_payload(response)
        if response.status_code == 499 and _requires_mfa(payload):
            return parse_mfa_challenge(response.status_code, payload)
        if response.status_code >= 400:
            raise _failure("AUTHENTICATION_REJECTED" if response.status_code == 401 else "AUTHENTICATION_FAILED", response, payload)
        return self._success_response(response, payload)

    async def verify_2fa(self, request: TwoFactorRequest) -> LoginSuccessResponse:
        """Validate a one-time MFA token using the same login endpoint."""
        response = await self.login(request)
        if isinstance(response, MfaChallengeResponse):
            raise CertificateUploadError("UniFi returned another MFA challenge after token validation")
        return response

    async def upload_certificate(self, request: UploadCertificateRequest) -> UploadCertificateResponse:
        csrf = self._require_csrf()
        response = await self._post_json(
            "/api/userCertificates",
            request.to_payload(),
            "CERTIFICATE_UPLOAD_FAILED",
            headers={"X-Csrf-Token": csrf},
        )
        payload = parse_payload(response)
        if response.status_code >= 400:
            raise _failure("CERTIFICATE_UPLOAD_FAILED", response, payload)
        certificate_id = _certificate_id(payload)
        if certificate_id is None:
            raise CertificateUploadError("UniFi certificate upload returned no certificate ID")
        return UploadCertificateResponse(response.status_code, certificate_id, payload)

    async def activate_certificate(self, request: ActivateCertificateRequest) -> ActivateCertificateResponse:
        csrf = self._require_csrf()
        response = await self._put_json(
            f"/api/userCertificates/{request.certificate_id}/status",
            request.to_payload(),
            "CERTIFICATE_ACTIVATION_FAILED",
            headers={"X-Csrf-Token": csrf},
        )
        payload = parse_payload(response)
        if response.status_code >= 400:
            raise _failure("CERTIFICATE_ACTIVATION_FAILED", response, payload)
        return ActivateCertificateResponse(response.status_code, request.active, payload)

    async def create_api_key(self, request: CreateApiKeyRequest) -> CreateApiKeyResponse:
        csrf = self._require_csrf()
        response = await self._post_json(
            f"/proxy/users/api/v2/user/{request.user_id}/keys",
            request.to_payload(),
            "API_KEY_CREATION_FAILED",
            headers={"Content-Type": "text/plain;charset=UTF-8", "X-Csrf-Token": csrf},
        )
        payload = parse_payload(response)
        if response.status_code >= 400:
            raise _failure("API_KEY_CREATION_FAILED", response, payload)
        result = parse_api_key_response(response.status_code, payload)
        if not result.key.full_api_key:
            raise CertificateUploadError("UniFi API key creation returned no key")
        return result

    def _success_response(self, response: httpx.Response, payload: dict[str, Any]) -> LoginSuccessResponse:
        token = response.cookies.get("TOKEN") or self._http.cookies.get("TOKEN")
        csrf = response.headers.get("X-Csrf-Token") or _csrf_from_token(token)
        user = parse_user_profile(payload)
        user_id = user.user_id or _user_id_from_token(token)
        if csrf is None or token is None or user_id is None:
            raise CertificateUploadError("UniFi login returned incomplete session credentials")
        self._user_id = user_id
        self._session = SessionCredentials(
            token=token,
            csrf_token=csrf,
            updated_csrf_token=response.headers.get("X-Updated-Csrf-Token"),
            token_expire_time=response.headers.get("X-Token-Expire-Time"),
        )
        return LoginSuccessResponse(response.status_code, user, self._session, payload)

    def _require_csrf(self) -> str:
        if self._session is None or self._session.csrf_token is None:
            raise CertificateUploadError("UniFi Console is not authenticated")
        return self._session.csrf_token

    async def _post_json(self, path: str, payload: dict[str, Any], category: str, headers: dict[str, str] | None = None) -> httpx.Response:
        try:
            return await self._http.post(path, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            raise CertificateUploadError(f"[NETWORK_ERROR] UniFi web API unavailable ({type(exc).__name__})") from exc

    async def _put_json(self, path: str, payload: dict[str, Any], category: str, headers: dict[str, str] | None = None) -> httpx.Response:
        try:
            return await self._http.put(path, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            raise CertificateUploadError(f"[NETWORK_ERROR] UniFi web API unavailable ({type(exc).__name__})") from exc


def _requires_mfa(payload: dict[str, Any]) -> bool:
    meta = payload.get("meta")
    return (
        isinstance(meta, dict) and meta.get("msg") == "api.err.Ubic2faTokenRequired"
    ) or (
        payload.get("code") == "MFA_AUTH_REQUIRED"
        and isinstance(payload.get("data"), dict)
        and payload["data"].get("required") == "2fa"
    )


def _certificate_id(payload: dict[str, Any]) -> str | None:
    direct = payload.get("id")
    if isinstance(direct, str) and direct:
        return direct
    data = payload.get("data")
    nested = data.get("id") if isinstance(data, dict) else None
    return nested if isinstance(nested, str) and nested else None


def _failure(category: str, response: httpx.Response, payload: dict[str, Any]) -> CertificateUploadError:
    meta = payload.get("meta")
    upstream = meta.get("msg") if isinstance(meta, dict) else payload.get("code")
    detail = f"; UniFi code: {upstream}" if isinstance(upstream, str) else ""
    return CertificateUploadError(f"[{category}] HTTP {response.status_code}{detail}", response.status_code)


def _csrf_from_token(token: str | None) -> str | None:
    payload = _jwt_payload(token)
    value = payload.get("csrfToken")
    return value if isinstance(value, str) and value else None


def _user_id_from_token(token: str | None) -> str | None:
    payload = _jwt_payload(token)
    value = payload.get("userId")
    return value if isinstance(value, str) and value else None


def _jwt_payload(token: str | None) -> dict[str, Any]:
    if not token:
        return {}
    try:
        encoded = token.split(".")[1]
        encoded += "=" * (-len(encoded) % 4)
        payload = json.loads(base64.urlsafe_b64decode(encoded).decode("utf-8"))
    except (IndexError, ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}
