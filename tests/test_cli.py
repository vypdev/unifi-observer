import stat

import pytest

from unifi_observer.cli import (
    CliError,
    _configure,
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
    from unifi_observer.infrastructure.certificate_uploader import TwoFactorRequiredError

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

    class FakeUploader:
        def __init__(self, base_url, timeout_seconds):
            assert base_url == settings.api_base_url
            assert timeout_seconds == settings.timeout_seconds

        async def authenticate(self, username, password, token=None):
            calls.append(("authenticate", username, password, token))
            if token is None:
                raise TwoFactorRequiredError("2FA required")

        async def upload_and_activate(self, **kwargs):
            calls.append(("upload", kwargs))

        async def aclose(self):
            calls.append(("close",))

    monkeypatch.setattr("unifi_observer.cli._prompt", lambda *args, **kwargs: next(prompts))
    monkeypatch.setattr("unifi_observer.cli.UniFiCertificateUploader", FakeUploader)

    _upload_local_certificate(settings, certificate, private_key)

    assert calls[0] == ("authenticate", "admin", "password", None)
    assert calls[1] == ("authenticate", "admin", "password", "123456")
    assert calls[2][0] == "upload"
    assert calls[-1] == ("close",)


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
