import stat
import subprocess
from pathlib import Path

import pytest

from scripts.generate_unifi_cert import CertificateRequest, generate_certificates, validate_request


def test_validate_request_requires_valid_ip_and_names():
    request = CertificateRequest(
        domain="unifi.local",
        ip_address="not-an-ip",
        organization="Efra Home Lab",
        common_name="unifi.local",
        output_dir=Path("certs"),
    )

    with pytest.raises(ValueError, match="IP address"):
        validate_request(request)


@pytest.mark.parametrize("domain", ["unifi.-local", "unifi-.local", "a..local"])
def test_validate_request_rejects_invalid_dns_labels(domain):
    request = CertificateRequest(
        domain=domain,
        ip_address="192.0.2.10",
        organization="Test Lab",
        common_name="unifi.local",
        output_dir=Path("certs"),
    )

    with pytest.raises(ValueError, match="DNS name"):
        validate_request(request)


def test_validate_request_rejects_subject_separator_injection():
    request = CertificateRequest(
        domain="unifi.local",
        ip_address="192.0.2.10",
        organization="Test/OU=Injected",
        common_name="unifi.local",
        output_dir=Path("certs"),
    )

    with pytest.raises(ValueError, match="separators"):
        validate_request(request)


def test_generate_certificates_creates_expected_files_and_permissions(tmp_path):
    request = CertificateRequest(
        domain="unifi.local",
        ip_address="192.0.2.10",
        organization="Test Lab",
        common_name="unifi.local",
        output_dir=tmp_path / "certs",
    )

    generated = generate_certificates(request)

    assert {path.name for path in generated} == {
        "unifi-local-ca.key",
        "unifi-local-ca.crt",
        "unifi.local.key",
        "unifi.local.csr",
        "unifi.local.crt",
        "unifi.local.fullchain.crt",
    }
    assert stat.S_IMODE((request.output_dir / "unifi-local-ca.key").stat().st_mode) == 0o600
    assert stat.S_IMODE((request.output_dir / "unifi.local.key").stat().st_mode) == 0o600
    assert "BEGIN CERTIFICATE" in (request.output_dir / "unifi.local.crt").read_text()

    certificate = subprocess.run(
        [
            "openssl",
            "x509",
            "-in",
            str(request.output_dir / "unifi.local.crt"),
            "-noout",
            "-ext",
            "subjectAltName",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "DNS:unifi.local" in certificate.stdout
    assert "IP Address:192.0.2.10" in certificate.stdout


def test_generate_certificates_does_not_overwrite_without_force(tmp_path):
    request = CertificateRequest(
        domain="unifi.local",
        ip_address="192.0.2.10",
        organization="Test Lab",
        common_name="unifi.local",
        output_dir=tmp_path / "certs",
    )

    generate_certificates(request)

    with pytest.raises(FileExistsError, match="already exists"):
        generate_certificates(request)


def test_generate_certificates_force_replaces_complete_set(tmp_path):
    request = CertificateRequest(
        domain="unifi.local",
        ip_address="192.0.2.10",
        organization="Test Lab",
        common_name="unifi.local",
        output_dir=tmp_path / "certs",
    )

    generate_certificates(request)
    old_certificate = (request.output_dir / "unifi.local.crt").read_bytes()
    generate_certificates(CertificateRequest(**{**request.__dict__, "force": True}))

    new_files = {path.name for path in request.output_dir.iterdir()}
    assert new_files == {
        "unifi-local-ca.key",
        "unifi-local-ca.crt",
        "unifi.local.key",
        "unifi.local.csr",
        "unifi.local.crt",
        "unifi.local.fullchain.crt",
    }
    assert (request.output_dir / "unifi.local.crt").read_bytes() != old_certificate
