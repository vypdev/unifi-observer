import base64
import json

import httpx
import pytest

from unifi_observer.infrastructure.certificate_uploader import (
    CertificateUploadError,
    TwoFactorRequiredError,
    UniFiCertificateUploader,
)


def jwt_with_csrf(value: str) -> str:
    payload = base64.urlsafe_b64encode(
        json.dumps({"csrfToken": value, "userId": "user-1"}).encode()
    ).decode().rstrip("=")
    return f"header.{payload}.signature"


@pytest.mark.asyncio
async def test_upload_and_activate_uses_local_console_web_contract():
    token = jwt_with_csrf("csrf-test")
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.method == "POST" and request.url.path == "/api/auth/login":
            assert json.loads(request.content) == {
                "username": "admin",
                "password": "password",
                "rememberMe": False,
            }
            return httpx.Response(
                200,
                json={"meta": {"rc": "ok"}},
                headers={"set-cookie": f"TOKEN={token}; Path=/; HttpOnly"},
            )
        if request.method == "POST" and request.url.path == "/api/userCertificates":
            assert request.headers["x-csrf-token"] == "csrf-test"
            assert json.loads(request.content) == {
                "name": "unifi.local",
                "cert": "CERTIFICATE",
                "key": "PRIVATE-KEY",
            }
            return httpx.Response(200, json={"id": "certificate-1"})
        if request.method == "PUT" and request.url.path == "/api/userCertificates/certificate-1/status":
            assert request.headers["x-csrf-token"] == "csrf-test"
            assert json.loads(request.content) == {"active": True}
            return httpx.Response(200, json={"meta": {"rc": "ok"}})
        if request.method == "POST" and request.url.path == "/proxy/users/api/v2/user/user-1/keys":
            assert request.headers["content-type"] == "text/plain;charset=UTF-8"
            assert request.headers["x-csrf-token"] == "csrf-test"
            assert json.loads(request.content) == {
                "name": "unifi-observer",
                "description": "UniFi Observer local integration key",
            }
            return httpx.Response(200, json={"data": {"full_api_key": "generated-key"}})
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    uploader = UniFiCertificateUploader(
        "https://unifi.local",
        transport=httpx.MockTransport(handler),
    )
    await uploader.authenticate("admin", "password")
    await uploader.upload_and_activate(
        certificate_name="unifi.local",
        certificate_pem="CERTIFICATE",
        private_key_pem="PRIVATE-KEY",
    )
    assert await uploader.create_api_key("unifi-observer", "UniFi Observer local integration key") == "generated-key"
    await uploader.aclose()

    assert [request.url.path for request in calls] == [
        "/api/auth/login",
        "/api/userCertificates",
        "/api/userCertificates/certificate-1/status",
        "/proxy/users/api/v2/user/user-1/keys",
    ]


@pytest.mark.asyncio
async def test_authentication_reports_http_status_without_secrets():
    uploader = UniFiCertificateUploader(
        "https://unifi.local",
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                401,
                json={"meta": {"msg": "api.err.InvalidCredentials"}},
            ),
        ),
    )

    with pytest.raises(CertificateUploadError, match=r"AUTHENTICATION_REJECTED.*HTTP 401") as error:
        await uploader.authenticate("admin", "super-secret-value")
    assert "super-secret-value" not in str(error.value)
    await uploader.aclose()


@pytest.mark.asyncio
async def test_upload_rejects_login_without_token():
    uploader = UniFiCertificateUploader(
        "https://unifi.local",
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                499,
                json={"meta": {"msg": "api.err.Ubic2faTokenRequired"}},
            ),
        ),
    )

    with pytest.raises(TwoFactorRequiredError, match="2FA"):
        await uploader.authenticate("admin", "password")
    await uploader.aclose()


@pytest.mark.asyncio
async def test_authentication_recognizes_sso_mfa_challenge_and_clears_cookie():
    uploader = UniFiCertificateUploader(
        "https://unifi.local",
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                499,
                json={
                    "code": "MFA_AUTH_REQUIRED",
                    "message": "MFA token required to authenticate to SSO",
                    "data": {
                        "required": "2fa",
                        "mfaCookie": "mfa-cookie-placeholder",
                    },
                },
            ),
        ),
    )

    with pytest.raises(TwoFactorRequiredError) as error:
        await uploader.authenticate("admin", "password")
    assert error.value.sso is True
    assert uploader._mfa_cookie == "mfa-cookie-placeholder"
    await uploader.aclose()
    assert uploader._mfa_cookie is None


@pytest.mark.asyncio
async def test_authentication_resubmits_token_after_2fa_challenge():
    token = jwt_with_csrf("csrf-2fa")
    attempts = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        attempts.append(payload)
        if "token" not in payload:
            return httpx.Response(
                499,
                json={"meta": {"msg": "api.err.Ubic2faTokenRequired"}},
            )
        assert payload["token"] == "123456"
        return httpx.Response(
            200,
            headers={"set-cookie": f"TOKEN={token}; Path=/; HttpOnly"},
        )

    uploader = UniFiCertificateUploader(
        "https://unifi.local",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(TwoFactorRequiredError):
        await uploader.authenticate("admin", "password")
    await uploader.authenticate("admin", "password", "123456")
    await uploader.aclose()

    assert attempts == [
        {"username": "admin", "password": "password", "rememberMe": False},
        {
            "username": "admin",
            "password": "password",
            "rememberMe": False,
            "token": "123456",
        },
    ]
