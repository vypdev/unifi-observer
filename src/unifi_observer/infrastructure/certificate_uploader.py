"""Temporary UniFi OS web-console adapter for certificate activation."""

from __future__ import annotations

import base64
import json
from typing import Any

import httpx

from ..domain.errors import UniFiError


class CertificateUploadError(UniFiError):
    """Raised when the UniFi OS web certificate workflow cannot complete."""


class TwoFactorRequiredError(CertificateUploadError):
    """Raised when UniFi requires a one-time authentication token."""

    def __init__(self, message: str, status_code: int | None = None, *, sso: bool = False):
        super().__init__(message, status_code)
        self.sso = sso


class UniFiCertificateUploader:
    """Use the UniFi OS web-console certificate workflow during bootstrap.

    This is intentionally separate from the read-only Network Integration client.
    UniFi exposes this workflow through the web console rather than the official
    Network API, so endpoint compatibility must be verified against the console
    firmware before enabling it in a deployment.
    """

    def __init__(
        self,
        base_url: str,
        timeout_seconds: float = 15.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        if not base_url.startswith("https://"):
            raise ValueError("certificate upload requires an HTTPS UniFi Console URL")
        self._http = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout_seconds,
            # Bootstrap-only exception: UniFi's factory certificate is not trusted
            # or hostname-valid in the local network. The next connection uses
            # the generated CA with normal TLS verification enabled.
            verify=False,
            transport=transport,
        )
        self._csrf_token: str | None = None
        self._user_id: str | None = None
        self._mfa_cookie: str | None = None

    async def aclose(self) -> None:
        await self._http.aclose()
        self._csrf_token = None
        self._user_id = None
        self._mfa_cookie = None

    async def upload_and_activate(
        self,
        *,
        certificate_name: str,
        certificate_pem: str,
        private_key_pem: str,
    ) -> None:
        csrf_token = self._csrf_token
        if csrf_token is None:
            raise CertificateUploadError("UniFi Console is not authenticated")
        certificate_id = await self._upload(
            certificate_name,
            certificate_pem,
            private_key_pem,
            csrf_token,
        )
        await self._activate(certificate_id, csrf_token)

    async def create_api_key(self, name: str, description: str) -> str:
        if self._csrf_token is None or self._user_id is None:
            raise CertificateUploadError("UniFi Console is not authenticated")
        try:
            response = await self._http.post(
                f"/proxy/users/api/v2/user/{self._user_id}/keys",
                headers={
                    "Content-Type": "text/plain;charset=UTF-8",
                    "X-Csrf-Token": self._csrf_token,
                },
                content=json.dumps({"name": name, "description": description}),
            )
        except httpx.HTTPError as exc:
            raise CertificateUploadError(f"[NETWORK_ERROR] UniFi API key creation unavailable ({type(exc).__name__})") from exc
        if response.status_code >= 400:
            raise CertificateUploadError(_http_failure("API_KEY_CREATION_FAILED", response))
        try:
            payload: Any = response.json()
        except ValueError as exc:
            raise CertificateUploadError("UniFi API key creation returned invalid JSON") from exc
        data = payload.get("data") if isinstance(payload, dict) else None
        api_key = data.get("full_api_key") if isinstance(data, dict) else None
        if not isinstance(api_key, str) or not api_key:
            raise CertificateUploadError("UniFi API key creation returned no key")
        return api_key

    async def authenticate(
        self,
        username: str,
        password: str,
        two_factor_token: str | None = None,
    ) -> None:
        payload = {
            "username": username,
            "password": password,
            "token": two_factor_token or "",
            "rememberMe": False,
        }
        try:
            response = await self._http.post(
                "/api/auth/login",
                json=payload,
            )
        except httpx.HTTPError as exc:
            raise CertificateUploadError(f"[NETWORK_ERROR] UniFi login unavailable ({type(exc).__name__})") from exc
        response_payload = _response_json(response)
        if response.status_code == 499 and _requires_two_factor(response_payload):
            self._mfa_cookie = _mfa_cookie_from_payload(response_payload)
            is_sso_mfa = response_payload.get("code") == "MFA_AUTH_REQUIRED"
            message = (
                "[TWO_FACTOR_REQUIRED] UniFi SSO requires a 2FA verification step"
                if is_sso_mfa
                else "[TWO_FACTOR_REQUIRED] UniFi Console requires a 2FA token"
            )
            raise TwoFactorRequiredError(message, response.status_code, sso=is_sso_mfa)
        if response.status_code >= 400:
            if response.status_code == 401:
                raise CertificateUploadError(
                    f"{_http_failure('AUTHENTICATION_REJECTED', response)}: "
                    "UniFi rejected the username/password or the account is not permitted "
                    "for local console login"
                )
            raise CertificateUploadError(_http_failure("AUTHENTICATION_FAILED", response))

        csrf_header = response.headers.get("x-csrf-token")
        token = response.cookies.get("TOKEN") or self._http.cookies.get("TOKEN")
        self._csrf_token = csrf_header or (_csrf_from_token(token) if token else None)
        self._user_id = _user_id_from_token(token) if token else None
        if self._csrf_token is None:
            raise CertificateUploadError("UniFi Console login returned no CSRF token")
        self._mfa_cookie = None

    async def _upload(
        self,
        certificate_name: str,
        certificate_pem: str,
        private_key_pem: str,
        csrf_token: str,
    ) -> str:
        try:
            response = await self._http.post(
                "/api/userCertificates",
                headers={"X-Csrf-Token": csrf_token},
                json={
                    "name": certificate_name,
                    "cert": certificate_pem,
                    "key": private_key_pem,
                },
            )
        except httpx.HTTPError as exc:
            raise CertificateUploadError(f"[NETWORK_ERROR] Certificate upload unavailable ({type(exc).__name__})") from exc
        if response.status_code >= 400:
            raise CertificateUploadError(_http_failure("CERTIFICATE_UPLOAD_FAILED", response))
        certificate_id = _certificate_id(response)
        if not certificate_id:
            raise CertificateUploadError("UniFi certificate upload returned no certificate ID")
        return certificate_id

    async def _activate(self, certificate_id: str, csrf_token: str) -> None:
        try:
            response = await self._http.put(
                f"/api/userCertificates/{certificate_id}/status",
                headers={"X-Csrf-Token": csrf_token},
                json={"active": True},
            )
        except httpx.HTTPError as exc:
            raise CertificateUploadError(f"[NETWORK_ERROR] Certificate activation unavailable ({type(exc).__name__})") from exc
        if response.status_code >= 400:
            raise CertificateUploadError(_http_failure("CERTIFICATE_ACTIVATION_FAILED", response))


def _csrf_from_token(token: str) -> str:
    try:
        encoded_payload = token.split(".")[1]
        encoded_payload += "=" * (-len(encoded_payload) % 4)
        payload = json.loads(base64.urlsafe_b64decode(encoded_payload).decode("utf-8"))
        csrf_token = payload.get("csrfToken")
    except (IndexError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CertificateUploadError("UniFi Console TOKEN did not contain a valid CSRF token") from exc
    if not isinstance(csrf_token, str) or not csrf_token:
        raise CertificateUploadError("UniFi Console TOKEN did not contain a CSRF token")
    return csrf_token


def _user_id_from_token(token: str) -> str:
    try:
        encoded_payload = token.split(".")[1]
        encoded_payload += "=" * (-len(encoded_payload) % 4)
        payload = json.loads(base64.urlsafe_b64decode(encoded_payload).decode("utf-8"))
        user_id = payload.get("userId")
    except (IndexError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CertificateUploadError("UniFi Console TOKEN did not contain a valid user ID") from exc
    if not isinstance(user_id, str) or not user_id:
        raise CertificateUploadError("UniFi Console TOKEN did not contain a user ID")
    return user_id


def _certificate_id(response: httpx.Response) -> str | None:
    try:
        payload: Any = response.json()
    except ValueError as exc:
        raise CertificateUploadError("UniFi certificate upload returned invalid JSON") from exc
    if not isinstance(payload, dict):
        return None
    direct_id = payload.get("id")
    if isinstance(direct_id, str) and direct_id:
        return direct_id
    data = payload.get("data")
    if isinstance(data, dict) and isinstance(data.get("id"), str) and data["id"]:
        return data["id"]
    return None


def _http_failure(category: str, response: httpx.Response) -> str:
    payload = _response_json(response)
    upstream_code: str | None = None
    meta = payload.get("meta")
    if isinstance(meta, dict) and isinstance(meta.get("msg"), str):
        upstream_code = meta["msg"]
    elif isinstance(payload.get("codeS"), str):
        upstream_code = payload["codeS"]
    elif isinstance(payload.get("msg"), str):
        upstream_code = payload["msg"]
    detail = f"; UniFi code: {upstream_code}" if upstream_code else ""
    return f"[{category}] HTTP {response.status_code}{detail}"


def _response_json(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _requires_two_factor(payload: dict[str, Any]) -> bool:
    meta = payload.get("meta")
    if isinstance(meta, dict) and meta.get("msg") == "api.err.Ubic2faTokenRequired":
        return True
    return payload.get("code") == "MFA_AUTH_REQUIRED" and isinstance(payload.get("data"), dict) and payload["data"].get("required") == "2fa"


def _mfa_cookie_from_payload(payload: dict[str, Any]) -> str | None:
    data = payload.get("data")
    if not isinstance(data, dict):
        return None
    cookie = data.get("mfaCookie")
    return cookie if isinstance(cookie, str) and cookie else None
