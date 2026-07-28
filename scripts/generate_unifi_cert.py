#!/usr/bin/env python3
"""Generate a local CA and a UniFi server certificate with DNS/IP SANs."""

from __future__ import annotations

import argparse
import ipaddress
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

_DOMAIN_LABEL_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?$")


@dataclass(frozen=True)
class CertificateRequest:
    domain: str
    ip_address: str
    organization: str
    common_name: str
    output_dir: Path
    server_days: int = 825
    ca_days: int = 3650
    force: bool = False


def validate_request(request: CertificateRequest) -> None:
    labels = request.domain.rstrip(".").split(".")
    if (
        not labels
        or len(request.domain.rstrip(".")) > 253
        or any(len(label) > 63 or not _DOMAIN_LABEL_PATTERN.fullmatch(label) for label in labels)
    ):
        raise ValueError("domain must be a valid DNS name")
    try:
        ipaddress.ip_address(request.ip_address)
    except ValueError as exc:
        raise ValueError("IP address must be a valid IPv4 or IPv6 address") from exc
    for label, value in (("organization", request.organization), ("common name", request.common_name)):
        if not value.strip() or any(char in value for char in "/\\\r\n\x00"):
            raise ValueError(f"{label} must be non-empty and contain no separators or control characters")
    if request.server_days <= 0 or request.ca_days <= 0:
        raise ValueError("certificate validity periods must be positive")


def expected_files(request: CertificateRequest) -> tuple[Path, ...]:
    prefix = request.output_dir
    return (
        prefix / "unifi-local-ca.key",
        prefix / "unifi-local-ca.crt",
        prefix / f"{request.domain}.key",
        prefix / f"{request.domain}.csr",
        prefix / f"{request.domain}.crt",
        prefix / f"{request.domain}.fullchain.crt",
    )


def generate_certificates(request: CertificateRequest) -> tuple[Path, ...]:
    """Generate certificate files using the system OpenSSL executable."""
    validate_request(request)
    output_dir = request.output_dir.expanduser()
    request = CertificateRequest(**{**request.__dict__, "output_dir": output_dir})
    files = expected_files(request)
    if not request.force:
        existing = [path for path in files if path.exists()]
        if existing:
            raise FileExistsError(f"output file already exists: {existing[0]}")

    output_dir.mkdir(parents=True, exist_ok=True)
    output_dir.chmod(0o700)
    temp_dir = Path(tempfile.mkdtemp(prefix=".unifi-cert-", dir=output_dir.parent))
    try:
        temp_request = CertificateRequest(**{**request.__dict__, "output_dir": temp_dir})
        _generate_in_directory(temp_request)
        for source in expected_files(temp_request):
            source.chmod(0o600 if source.suffix == ".key" else 0o644)
        _install_files(temp_request, request, files)
        return files
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def _install_files(staged_request: CertificateRequest, request: CertificateRequest, files: tuple[Path, ...]) -> None:
    staged_files = expected_files(staged_request)
    backup_dir = Path(tempfile.mkdtemp(prefix=".unifi-cert-backup-", dir=request.output_dir.parent))
    backed_up: list[tuple[Path, Path]] = []
    installed: list[Path] = []
    try:
        if request.force:
            for destination in files:
                if destination.exists():
                    backup = backup_dir / destination.name
                    os.replace(destination, backup)
                    backed_up.append((backup, destination))
        for source, destination in zip(staged_files, files):
            os.replace(source, destination)
            installed.append(destination)
    except OSError:
        for destination in installed:
            destination.unlink(missing_ok=True)
        for backup, destination in reversed(backed_up):
            os.replace(backup, destination)
        raise
    finally:
        shutil.rmtree(backup_dir, ignore_errors=True)


def _generate_in_directory(request: CertificateRequest) -> None:
    output_dir = request.output_dir
    ca_key = output_dir / "unifi-local-ca.key"
    ca_cert = output_dir / "unifi-local-ca.crt"
    server_key = output_dir / f"{request.domain}.key"
    csr = output_dir / f"{request.domain}.csr"
    server_cert = output_dir / f"{request.domain}.crt"
    fullchain = output_dir / f"{request.domain}.fullchain.crt"
    extension_file = output_dir / "server.ext"
    serial_file = output_dir / "unifi-local-ca.srl"

    _run(["openssl", "genrsa", "-out", str(ca_key), "4096"])
    _run(
        [
            "openssl",
            "req",
            "-x509",
            "-new",
            "-nodes",
            "-key",
            str(ca_key),
            "-sha256",
            "-days",
            str(request.ca_days),
            "-out",
            str(ca_cert),
            "-subj",
            f"/O={request.organization}/CN={request.organization} Local CA",
            "-addext",
            "basicConstraints=critical,CA:TRUE,pathlen:1",
            "-addext",
            "keyUsage=critical,keyCertSign,cRLSign",
            "-addext",
            "subjectKeyIdentifier=hash",
        ]
    )
    _run(["openssl", "genrsa", "-out", str(server_key), "2048"])
    _run(
        [
            "openssl",
            "req",
            "-new",
            "-key",
            str(server_key),
            "-out",
            str(csr),
            "-subj",
            f"/O={request.organization}/CN={request.common_name}",
        ]
    )
    extension_file.write_text(
        "\n".join(
            (
                "basicConstraints=critical,CA:FALSE",
                "keyUsage=critical,digitalSignature,keyEncipherment",
                "extendedKeyUsage=serverAuth",
                f"subjectAltName=DNS:{request.domain},IP:{request.ip_address}",
            )
        )
        + "\n",
        encoding="ascii",
    )
    _run(
        [
            "openssl",
            "x509",
            "-req",
            "-in",
            str(csr),
            "-CA",
            str(ca_cert),
            "-CAkey",
            str(ca_key),
            "-CAcreateserial",
            "-CAserial",
            str(serial_file),
            "-out",
            str(server_cert),
            "-days",
            str(request.server_days),
            "-sha256",
            "-extfile",
            str(extension_file),
        ]
    )
    fullchain.write_bytes(server_cert.read_bytes() + ca_cert.read_bytes())
    extension_file.unlink(missing_ok=True)
    serial_file.unlink(missing_ok=True)


def _run(command: list[str]) -> None:
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise RuntimeError("openssl executable was not found") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or "").strip().splitlines()
        raise RuntimeError(detail[-1] if detail else "openssl command failed") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--domain", help="DNS name in the server certificate")
    parser.add_argument("--ip", help="IPv4 or IPv6 address in the server certificate")
    parser.add_argument("--organization", help="X.509 organization (O)")
    parser.add_argument("--common-name", help="X.509 common name (CN)")
    parser.add_argument("--output-dir", default="./unifi-certs", help="output directory")
    parser.add_argument("--server-days", type=int, default=825, help="server certificate validity")
    parser.add_argument("--ca-days", type=int, default=3650, help="CA certificate validity")
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="require all identity values from command-line options",
    )
    parser.add_argument("--force", action="store_true", help="replace files with the same names")
    args = parser.parse_args()
    values = (args.domain, args.ip, args.organization, args.common_name)
    if (args.non_interactive or not sys.stdin.isatty()) and any(value is None for value in values):
        parser.error("--non-interactive requires --domain, --ip, --organization, and --common-name")
    try:
        request = CertificateRequest(
            domain=args.domain or input("DNS domain: ").strip(),
            ip_address=args.ip or input("IP address: ").strip(),
            organization=args.organization or input("Organization (O): ").strip(),
            common_name=args.common_name or input("Common Name (CN): ").strip(),
            output_dir=Path(args.output_dir),
            server_days=args.server_days,
            ca_days=args.ca_days,
            force=args.force,
        )
        request = CertificateRequest(**{**request.__dict__, "output_dir": request.output_dir.expanduser()})
        generated = generate_certificates(request)
    except (EOFError, KeyboardInterrupt):
        parser.error("input cancelled")
    except (OSError, ValueError, FileExistsError, RuntimeError) as exc:
        parser.error(str(exc))

    print("\nCertificates generated successfully:")
    for path in generated:
        print(f"  - {path}")
    print("\nNext steps:")
    print(f"  1. Upload {request.domain}.fullchain.crt and {request.domain}.key to the UniFi console.")
    print(f"  2. Install {request.output_dir / 'unifi-local-ca.crt'} as a trusted CA on the MCP host.")
    print(f"  3. Resolve {request.domain} to {request.ip_address} on the MCP host.")
    print(f"  4. Use https://{request.domain} and keep UNIFI_VERIFY_TLS=true.")
    print("  5. Keep all .key files private; never commit them to Git.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
