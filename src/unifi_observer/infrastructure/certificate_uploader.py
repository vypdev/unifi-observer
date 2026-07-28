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

    async def aclose(self) -> None:
        await self._http.aclose()

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

    async def authenticate(
        self,
        username: str,
        password: str,
        two_factor_token: str | None = None,
    ) -> None:
        payload = {"username": username, "password": password, "rememberMe": False}
        if two_factor_token:
            payload["token"] = two_factor_token
        try:
            response = await self._http.post(
                "/api/auth/login",
                json=payload,
            )
        except httpx.HTTPError as exc:
            raise CertificateUploadError("UniFi Console login was unavailable") from exc
        response_payload = _response_json(response)
        if response.status_code == 499 and _requires_two_factor(response_payload):
            raise TwoFactorRequiredError("UniFi Console requires a 2FA token", response.status_code)
        if response.status_code >= 400:
            raise CertificateUploadError("UniFi Console login was rejected", response.status_code)

        csrf_header = response.headers.get("x-csrf-token")
        token = response.cookies.get("TOKEN") or self._http.cookies.get("TOKEN")
        self._csrf_token = csrf_header or (_csrf_from_token(token) if token else None)
        if self._csrf_token is None:
            raise CertificateUploadError("UniFi Console login returned no CSRF token")

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
            raise CertificateUploadError("UniFi certificate upload was unavailable") from exc
        if response.status_code >= 400:
            raise CertificateUploadError("UniFi certificate upload was rejected", response.status_code)
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
            raise CertificateUploadError("UniFi certificate activation was unavailable") from exc
        if response.status_code >= 400:
            raise CertificateUploadError("UniFi certificate activation was rejected", response.status_code)


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


def _response_json(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _requires_two_factor(payload: dict[str, Any]) -> bool:
    meta = payload.get("meta")
    return isinstance(meta, dict) and meta.get("msg") == "api.err.Ubic2faTokenRequired"
