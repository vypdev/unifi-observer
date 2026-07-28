import stat

import pytest

from unifi_observer.cli import (
    CliError,
    _configure,
    _generate_local_certificates,
    _prepare_local_tls,
    build_parser,
    load_env_file,
    write_env_file,
)
from unifi_observer.infrastructure.config import Settings


def test_parser_exposes_observer_commands():
    parser = build_parser()
    for command in (
        "get-site",
        "generate-certificate",
        "configure",
        "start",
        "stop",
        "restart",
        "status",
        "uninstall",
    ):
        args = parser.parse_args([command])
        assert args.command == command


def test_write_and_load_env_file_protects_api_key(tmp_path):
    path = tmp_path / "config.env"
    values = {
        "UNIFI_API_MODE": "local",
        "UNIFI_API_BASE_URL": "https://unifi.local",
        "UNIFI_API_KEY": "secret-'key\\\\with\"punctuation",
        "UNIFI_SITE_ID": "site-123",
    }

    write_env_file(path, values)

    assert load_env_file(path) == values
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert "UNIFI_API_KEY=" in path.read_text()


def test_write_env_file_refuses_parent_that_is_not_private(tmp_path):
    path = tmp_path / "config.env"
    path.parent.chmod(0o755)

    with pytest.raises(PermissionError, match="private"):
        write_env_file(path, {"UNIFI_API_KEY": "secret"})


def test_prepare_local_tls_generates_ca_and_returns_verify_settings(monkeypatch, tmp_path):
    settings = Settings(
        api_mode="local",
        api_base_url="https://unifi.local",
        api_key="secret",
        site_id=None,
        allowed_site_ids=(),
        verify_tls=False,
        timeout_seconds=15,
        enable_write=False,
    )
    answers = iter(["yes", "yes", "no", ""])
    generated = tmp_path / "ca.crt"
    generated.write_text("CA", encoding="utf-8")
    private_key = tmp_path / "server.key"
    private_key.write_text("KEY", encoding="utf-8")
    monkeypatch.setattr("unifi_observer.cli._prompt", lambda *args, **kwargs: next(answers))
    monkeypatch.setattr(
        "unifi_observer.cli._generate_local_certificates",
        lambda _: (tmp_path / "server.fullchain.crt", private_key, generated),
    )

    configured = _prepare_local_tls(settings, tmp_path / "config.env")

    assert configured.verify_tls is True
    assert configured.ca_cert_path == str(generated)


def test_prepare_local_tls_can_be_skipped(monkeypatch, tmp_path):
    settings = Settings(
        api_mode="local",
        api_base_url="https://unifi.local",
        api_key="secret",
        site_id=None,
        allowed_site_ids=(),
        verify_tls=True,
        timeout_seconds=15,
        enable_write=False,
    )
    monkeypatch.setattr("unifi_observer.cli._prompt", lambda *args, **kwargs: "no")
    monkeypatch.setattr(
        "unifi_observer.cli._generate_local_certificates",
        lambda _: pytest.fail("certificate generation should be skipped"),
    )

    configured = _prepare_local_tls(settings, tmp_path / "config.env")

    assert configured.verify_tls is False
    assert configured.ca_cert_path is None


def test_upload_local_certificate_prompts_for_2fa_only_after_challenge(monkeypatch, tmp_path):
    from unifi_observer.cli import _upload_local_certificate
    from unifi_observer.domain.unifi_web_api_models import (
        ActivateCertificateResponse,
        LoginSuccessResponse,
        MfaChallengeResponse,
        SessionCredentials,
        UniFiUserProfile,
        UploadCertificateResponse,
    )

    certificate = tmp_path / "unifi.local.fullchain.crt"
    private_key = tmp_path / "unifi.local.key"
    certificate.write_text("CERTIFICATE", encoding="utf-8")
    private_key.write_text("PRIVATE-KEY", encoding="utf-8")
    settings = Settings(
        api_mode="local",
        api_base_url="https://unifi.local",
        api_key="api-key",
        site_id=None,
        allowed_site_ids=(),
        verify_tls=True,
        timeout_seconds=15,
        enable_write=False,
    )
    prompts = iter(["admin", "password", "123456"])
    calls = []

    class FakeWebApi:
        def __init__(self, base_url, timeout_seconds):
            assert base_url == settings.api_base_url
            assert timeout_seconds == settings.timeout_seconds

        async def login(self, request):
            calls.append(("login", request))
            return MfaChallengeResponse(499, "MFA_AUTH_REQUIRED", "2FA required", "2fa")

        async def verify_2fa(self, request):
            calls.append(("verify_2fa", request))
            return LoginSuccessResponse(
                200,
                UniFiUserProfile("user-1", None, "admin", None, None, None, None, None, None, None, None),
                SessionCredentials(csrf_token="csrf"),
            )

        async def upload_certificate(self, request):
            calls.append(("upload", request))
            return UploadCertificateResponse(200, "certificate-1")

        async def activate_certificate(self, request):
            calls.append(("activate", request))
            return ActivateCertificateResponse(200, True)

        async def create_api_key(self, request):
            raise AssertionError("existing API key must skip creation")

        async def aclose(self):
            calls.append(("close",))

    monkeypatch.setattr("unifi_observer.cli._prompt", lambda *args, **kwargs: next(prompts))
    monkeypatch.setattr("unifi_observer.cli.UniFiWebApiClient", FakeWebApi)

    _upload_local_certificate(settings, certificate, private_key)

    assert [call[0] for call in calls] == ["login", "verify_2fa", "upload", "activate", "close"]
    assert calls[1][1].token == "123456"


def test_generate_local_certificates_reuses_existing_material(monkeypatch, tmp_path):
    config_path = tmp_path / "config.env"
    certificate_dir = config_path.parent / "certificates"
    certificate_dir.mkdir()
    certificate_dir.chmod(0o700)
    existing = {
        "unifi-local-ca.key": "CA-KEY",
        "unifi-local-ca.crt": "CA-CERT",
        "unifi.local.key": "SERVER-KEY",
        "unifi.local.csr": "CSR",
        "unifi.local.crt": "CERT",
        "unifi.local.fullchain.crt": "FULLCHAIN",
    }
    for name, content in existing.items():
        path = certificate_dir / name
        path.write_text(content, encoding="utf-8")
        if name.endswith(".key"):
            path.chmod(0o600)
    answers = iter(["unifi.local", "192.168.0.1", "UniFi Observer", "unifi.local", "reuse"])
    monkeypatch.setattr("unifi_observer.cli._prompt", lambda *args, **kwargs: next(answers))
    monkeypatch.setattr(
        "scripts.generate_unifi_cert.generate_certificates",
        lambda _: pytest.fail("reuse must not regenerate certificates"),
    )

    result = _generate_local_certificates(config_path)

    assert result == (
        certificate_dir / "unifi.local.fullchain.crt",
        certificate_dir / "unifi.local.key",
        certificate_dir / "unifi-local-ca.crt",
    )
    assert (certificate_dir / "unifi-local-ca.key").read_text() == "CA-KEY"


def test_generate_local_certificates_replacement_requires_explicit_confirmation(monkeypatch, tmp_path):
    config_path = tmp_path / "config.env"
    certificate_dir = config_path.parent / "certificates"
    certificate_dir.mkdir()
    certificate_dir.chmod(0o700)
    existing_key = certificate_dir / "unifi-local-ca.key"
    existing_key.write_text("OLD", encoding="utf-8")
    existing_key.chmod(0o600)
    answers = iter(["unifi.local", "192.168.0.1", "UniFi Observer", "unifi.local", "replace", "REPLACE"])
    monkeypatch.setattr("unifi_observer.cli._prompt", lambda *args, **kwargs: next(answers))
    generated_requests = []

    def fake_generate(request):
        generated_requests.append(request)
        return tuple(certificate_dir / name for name in (
            "unifi-local-ca.key", "unifi-local-ca.crt", "unifi.local.key",
            "unifi.local.csr", "unifi.local.crt", "unifi.local.fullchain.crt",
        ))

    monkeypatch.setattr("scripts.generate_unifi_cert.generate_certificates", fake_generate)

    _generate_local_certificates(config_path)

    assert len(generated_requests) == 1
    assert generated_requests[0].force is True


def test_generate_local_certificates_cancel_does_not_change_existing_material(monkeypatch, tmp_path):
    config_path = tmp_path / "config.env"
    certificate_dir = config_path.parent / "certificates"
    certificate_dir.mkdir()
    certificate_dir.chmod(0o700)
    existing_key = certificate_dir / "unifi-local-ca.key"
    existing_key.write_text("OLD", encoding="utf-8")
    existing_key.chmod(0o600)
    answers = iter(["unifi.local", "192.168.0.1", "UniFi Observer", "unifi.local", "replace", "NO"])
    monkeypatch.setattr("unifi_observer.cli._prompt", lambda *args, **kwargs: next(answers))

    with pytest.raises(CliError, match="cancelled"):
        _generate_local_certificates(config_path)

    assert existing_key.read_text() == "OLD"


def test_configure_does_not_persist_after_tls_verification_failure(monkeypatch, tmp_path):
    settings = Settings(
        api_mode="local",
        api_base_url="https://unifi.local",
        api_key="secret",
        site_id=None,
        allowed_site_ids=(),
        verify_tls=True,
        timeout_seconds=15,
        enable_write=False,
    )
    monkeypatch.setattr("unifi_observer.cli._prompt_settings", lambda: settings)
    monkeypatch.setattr("unifi_observer.cli._prepare_local_tls", lambda current, _: current)
    monkeypatch.setattr(
        "unifi_observer.cli._discover_sites",
        lambda _: (_ for _ in ()).throw(RuntimeError("certificate verify failed")),
    )
    monkeypatch.setattr(
        "unifi_observer.cli.write_env_file",
        lambda *_: pytest.fail("configuration must not be persisted after TLS failure"),
    )

    with pytest.raises(CliError, match="TLS connection verification failed"):
        _configure(tmp_path / "config.env")
