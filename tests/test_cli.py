import stat
import subprocess

import pytest

from unifi_observer.cli import (
    CliError,
    _configure,
    _generate_local_certificates,
    _prepare_local_tls,
    _update,
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
        "update",
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


def test_generate_certificate_uses_core_ultra_ip_as_default(monkeypatch, tmp_path):
    import scripts.generate_unifi_cert as generator

    prompts = []
    answers = iter(["unifi.local", "", "UniFi Observer", "unifi.local"])

    def prompt(label, default=None, **kwargs):
        prompts.append((label, default))
        return next(answers) or (default or "")

    captured = []
    monkeypatch.setattr("unifi_observer.cli._prompt", prompt)
    monkeypatch.setattr(generator, "validate_request", lambda request: captured.append(request))
    files = tuple(tmp_path / name for name in (
        "unifi-local-ca.key", "unifi-local-ca.crt", "unifi.local.key",
        "unifi.local.csr", "unifi.local.crt", "unifi.local.fullchain.crt",
    ))
    monkeypatch.setattr(generator, "expected_files", lambda request: files)
    monkeypatch.setattr(generator, "generate_certificates", lambda request: files)

    _generate_local_certificates(tmp_path / "config.env")

    assert captured[0].ip_address == "192.168.0.1"
    assert ("Certificate IP address", "192.168.0.1") in prompts


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
        ApiKeyMetadata,
        CreateApiKeyResponse,
        ListApiKeysResponse,
        ListCertificatesResponse,
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

        async def list_api_keys(self, request):
            calls.append(("list_keys", request))
            return ListApiKeysResponse(200, ())

        async def list_certificates(self, request):
            calls.append(("list_certificates", request))
            return ListCertificatesResponse(200, ())

        async def activate_certificate(self, request):
            calls.append(("activate", request))
            return ActivateCertificateResponse(200, True)

        async def create_api_key(self, request):
            calls.append(("create", request))
            return CreateApiKeyResponse(
                200,
                ApiKeyMetadata("key-1", request.name, request.description, None, None, full_api_key="generated-key"),
            )

        async def aclose(self):
            calls.append(("close",))

    monkeypatch.setattr("unifi_observer.cli._prompt", lambda *args, **kwargs: next(prompts))
    monkeypatch.setattr("unifi_observer.cli.UniFiWebApiClient", FakeWebApi)

    _upload_local_certificate(settings, certificate, private_key)

    assert [call[0] for call in calls] == [
        "login", "verify_2fa", "list_keys", "list_certificates", "upload", "activate", "create", "close"
    ]
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


def test_update_does_not_restart_when_installed_commit_matches(monkeypatch, tmp_path, capsys):
    commit = "a" * 40
    install_dir = tmp_path / "install"
    install_dir.mkdir()
    (install_dir / ".unifi-observer-commit").write_text(commit, encoding="utf-8")
    unit = tmp_path / "unifi-observer.service"
    unit.write_text("unit", encoding="utf-8")
    monkeypatch.setenv("UNIFI_OBSERVER_INSTALL_DIR", str(install_dir))
    monkeypatch.setattr("unifi_observer.cli._unit_path", lambda: unit)
    monkeypatch.setattr("unifi_observer.cli._git_remote_commit", lambda *_: commit)
    monkeypatch.setattr("unifi_observer.cli._systemctl", lambda _: pytest.fail("service must not be touched"))

    assert _update() == 0
    assert "Already up to date" in capsys.readouterr().out


def test_update_installs_new_commit_before_restarting_service(monkeypatch, tmp_path, capsys):
    old_commit = "a" * 40
    new_commit = "b" * 40
    install_dir = tmp_path / "install"
    install_dir.mkdir()
    (install_dir / ".unifi-observer-commit").write_text(old_commit, encoding="utf-8")
    unit = tmp_path / "unifi-observer.service"
    unit.write_text("unit", encoding="utf-8")
    monkeypatch.setenv("UNIFI_OBSERVER_INSTALL_DIR", str(install_dir))
    monkeypatch.setattr("unifi_observer.cli._unit_path", lambda: unit)
    monkeypatch.setattr("unifi_observer.cli._git_remote_commit", lambda *_: new_commit)
    events = []

    class TemporaryCheckout:
        def __init__(self, path):
            self.path = path

        def __enter__(self):
            self.path.mkdir()
            return str(self.path)

        def __exit__(self, *_):
            return False

    monkeypatch.setattr("unifi_observer.cli.tempfile.TemporaryDirectory", lambda **_: TemporaryCheckout(tmp_path / "update"))

    def fake_run(command, **kwargs):
        events.append(command[0:2])
        if command[:2] == ["git", "clone"]:
            checkout = tmp_path / "update" / "repository"
            checkout.mkdir()
            setup = checkout / "scripts" / "setup.sh"
            setup.parent.mkdir()
            setup.write_text("#!/bin/sh\n", encoding="utf-8")
            setup.chmod(0o700)
        elif command[:2] == ["bash", str(tmp_path / "update" / "repository" / "scripts" / "setup.sh")]:
            (install_dir / ".unifi-observer-commit").write_text(new_commit, encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr("unifi_observer.cli._run_external", fake_run)
    monkeypatch.setattr("unifi_observer.cli._systemctl", lambda action: events.append(["systemctl", action]) or 0)

    assert _update() == 0
    assert events[-2:] == [["systemctl", "restart"], ["systemctl", "is-active"]]
    assert "Updated and restarted successfully" in capsys.readouterr().out
