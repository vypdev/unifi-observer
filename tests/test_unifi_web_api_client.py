import base64
import json

import httpx
import pytest

from unifi_observer.domain.unifi_web_api_models import (
    ActivateCertificateRequest,
    CreateApiKeyRequest,
    DeleteApiKeyRequest,
    DeleteCertificateRequest,
    LoginRequest,
    MfaChallengeResponse,
    TwoFactorRequest,
    UploadCertificateRequest,
)
from unifi_observer.infrastructure.unifi_web_api_client import UniFiWebApiClient


def jwt_payload(payload: dict[str, str]) -> str:
    encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    return f"header.{encoded}.signature"


@pytest.mark.asyncio
async def test_typed_web_api_client_exposes_login_mfa_upload_activation_and_key():
    token = jwt_payload({"csrfToken": "csrf", "userId": "user-1"})
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path == "/api/auth/login":
            payload = json.loads(request.content)
            if not payload["token"]:
                return httpx.Response(
                    499,
                    json={
                        "code": "MFA_AUTH_REQUIRED",
                        "message": "MFA token required",
                        "data": {"required": "2fa", "mfaCookie": "temporary"},
                    },
                )
            return httpx.Response(
                200,
                json={
                    "id": "user-1",
                    "username": "admin",
                    "email": "admin@example.invalid",
                    "scopes": ["network"],
                },
                headers={
                    "set-cookie": f"TOKEN={token}; Path=/; HttpOnly",
                    "X-Csrf-Token": "csrf",
                    "X-Updated-Csrf-Token": "csrf-updated",
                    "X-Token-Expire-Time": "2099-01-01T00:00:00Z",
                },
            )
        if request.url.path == "/api/userCertificates":
            return httpx.Response(200, json={"id": "certificate-1", "name": "unifi.local"})
        if request.url.path.endswith("/status"):
            return httpx.Response(200, json={"active": True})
        if request.url.path.endswith("/keys"):
            return httpx.Response(
                200,
                json={"data": {"id": "key-1", "name": "unifi-observer", "full_api_key": "secret-key"}},
            )
        if request.method == "DELETE" and request.url.path == "/proxy/users/api/v2/keys/key-1":
            return httpx.Response(200, json={"code": 1, "codeS": "SUCCESS", "data": "success"})
        if request.method == "DELETE" and request.url.path == "/api/userCertificates/certificate-1":
            return httpx.Response(204)
        raise AssertionError(f"unexpected request: {request.url.path}")

    client = UniFiWebApiClient("https://unifi.local", transport=httpx.MockTransport(handler))
    challenge = await client.login(LoginRequest("admin", "password"))
    assert isinstance(challenge, MfaChallengeResponse)
    assert challenge.required == "2fa"
    assert challenge.mfa_cookie == "temporary"

    success = await client.verify_2fa(TwoFactorRequest("admin", "password", "123456"))
    assert success.user.user_id == "user-1"
    assert success.session.csrf_token == "csrf"
    assert success.session.token == token

    uploaded = await client.upload_certificate(
        UploadCertificateRequest("unifi.local", "CERTIFICATE", "PRIVATE-KEY")
    )
    assert uploaded.certificate_id == "certificate-1"
    activated = await client.activate_certificate(ActivateCertificateRequest(uploaded.certificate_id))
    assert activated.active is True

    created = await client.create_api_key(CreateApiKeyRequest("user-1", "unifi-observer", "integration"))
    assert created.key.key_id == "key-1"
    assert created.key.full_api_key == "secret-key"
    assert (await client.delete_api_key(DeleteApiKeyRequest("key-1"))).deleted is True
    assert (await client.delete_certificate(DeleteCertificateRequest("certificate-1"))).deleted is True
    assert calls == [
        "/api/auth/login",
        "/api/auth/login",
        "/api/userCertificates",
        "/api/userCertificates/certificate-1/status",
        "/proxy/users/api/v2/user/user-1/keys",
        "/proxy/users/api/v2/keys/key-1",
        "/api/userCertificates/certificate-1",
    ]
    await client.aclose()


@pytest.mark.asyncio
async def test_typed_request_repr_does_not_expose_secrets():
    request = LoginRequest("admin", "password-value", "123456")
    assert "password-value" not in repr(request)
    assert "123456" not in repr(request)
