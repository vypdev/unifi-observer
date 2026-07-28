"""Interactive lifecycle CLI for the native UniFi Observer service."""

from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import os
import shlex
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

from .application.bootstrap import UniFiConsoleBootstrap
from .domain.errors import CertificateUploadError, UniFiError
from .infrastructure.config import Settings
from .infrastructure.unifi_client import UniFiClient
from .infrastructure.unifi_web_api_client import UniFiWebApiClient

DEFAULT_CONFIG_PATH = Path("~/.config/unifi-observer/config.env").expanduser()


class CliError(RuntimeError):
    """Raised for actionable CLI errors."""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="unifi-observer", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (
        ("get-site", "list and select visible UniFi sites"),
        ("generate-certificate", "generate a local CA and UniFi server certificate"),
        ("configure", "interactively configure and prepare the native service"),
        ("start", "start the native user service"),
        ("stop", "stop the native user service"),
        ("restart", "restart the native user service"),
        ("status", "show native user service status"),
        ("uninstall", "remove the native service and configuration"),
    ):
        commands.add_parser(name, help=help_text)
    return parser


def write_env_file(path: Path, values: dict[str, str]) -> None:
    """Write a shell-compatible environment file with private permissions."""
    path = path.expanduser()
    _ensure_private_config_dir(path.parent)
    if path.parent.stat().st_mode & 0o077:
        raise PermissionError(f"configuration directory must be private: {path.parent}")
    for key, value in values.items():
        if not key or not key.replace("_", "").isalnum() or "\n" in value or "\r" in value:
            raise ValueError("configuration contains an invalid key or value")
    content = "\n".join(f'{key}="{_escape_systemd_value(value)}"' for key, value in values.items()) + "\n"
    temporary = path.with_suffix(f"{path.suffix}.tmp-{os.getpid()}")
    temporary.write_text(content, encoding="utf-8")
    temporary.chmod(0o600)
    os.replace(temporary, path)
    path.chmod(0o600)


def _ensure_private_config_dir(path: Path) -> None:
    path = path.expanduser()
    existed = path.exists()
    path.mkdir(parents=True, exist_ok=True)
    if not existed:
        path.chmod(0o700)
    if path.stat().st_mode & 0o077:
        raise PermissionError(f"configuration directory must be private: {path}")


def _escape_systemd_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def load_env_file(path: Path) -> dict[str, str]:
    path = path.expanduser()
    if path.stat().st_mode & 0o077:
        raise PermissionError(f"configuration file must be private: {path}")
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, raw_value = line.partition("=")
        if not separator:
            raise ValueError(f"invalid configuration line in {path}")
        parsed = shlex.split(raw_value, comments=False)
        values[key] = parsed[0] if parsed else ""
    return values


def _settings_from_values(values: dict[str, str]) -> Settings:
    settings = Settings(
        api_mode=values.get("UNIFI_API_MODE", "site-manager"),
        api_base_url=values.get("UNIFI_API_BASE_URL", "https://api.ui.com"),
        api_key=values.get("UNIFI_API_KEY") or None,
        site_id=values.get("UNIFI_SITE_ID") or None,
        allowed_site_ids=tuple(x for x in values.get("UNIFI_ALLOWED_SITE_IDS", "").split(",") if x),
        verify_tls=values.get("UNIFI_VERIFY_TLS", "true").lower() not in {"0", "false", "no"},
        ca_cert_path=values.get("UNIFI_CA_CERT_PATH") or None,
        timeout_seconds=float(values.get("UNIFI_TIMEOUT_SECONDS", "15")),
        enable_write=values.get("UNIFI_ENABLE_WRITE", "false").lower() in {"1", "true", "yes"},
        host=values.get("MCP_HOST", "127.0.0.1"),
        port=int(values.get("MCP_PORT", "8000")),
    )
    settings.validate()
    return settings


def _settings_to_values(settings: Settings) -> dict[str, str]:
    return {
        "UNIFI_API_MODE": settings.api_mode,
        "UNIFI_API_BASE_URL": settings.api_base_url,
        "UNIFI_API_KEY": settings.api_key or "",
        "UNIFI_SITE_ID": settings.site_id or "",
        "UNIFI_ALLOWED_SITE_IDS": ",".join(settings.allowed_site_ids),
        "UNIFI_VERIFY_TLS": str(settings.verify_tls).lower(),
        "UNIFI_CA_CERT_PATH": settings.ca_cert_path or "",
        "UNIFI_TIMEOUT_SECONDS": str(settings.timeout_seconds),
        "UNIFI_ENABLE_WRITE": str(settings.enable_write).lower(),
        "MCP_HOST": settings.host,
        "MCP_PORT": str(settings.port),
    }


def _prompt(label: str, default: str | None = None, secret: bool = False) -> str:
    suffix = f" [{default}]" if default is not None else ""
    value = getpass.getpass(f"{label}{suffix}: ") if secret else input(f"{label}{suffix}: ")
    value = value.strip()
    return value or (default or "")


def _prompt_settings() -> Settings:
    mode = _prompt("API mode (site-manager/local)", "site-manager").lower()
    base_url = _prompt(
        "UniFi API base URL",
        "https://api.ui.com" if mode == "site-manager" else "https://unifi.local",
    )
    api_key_label = (
        "UniFi API key (leave empty to generate automatically)"
        if mode == "local"
        else "UniFi API key"
    )
    api_key = _prompt(api_key_label, secret=True)
    host = _prompt("MCP bind host", "127.0.0.1")
    port = int(_prompt("MCP port", "8000"))
    verify_tls = _prompt("Verify TLS (true/false)", "true").lower() not in {"0", "false", "no"}
    return Settings(
        api_mode=mode,
        api_base_url=base_url,
        api_key=api_key or None,
        site_id=None,
        allowed_site_ids=(),
        verify_tls=verify_tls,
        timeout_seconds=15,
        enable_write=False,
        host=host,
        port=port,
    )


def _run_async(operation: Any) -> Any:
    return asyncio.run(operation)


def _extract_sites(payload: Any) -> list[dict[str, Any]]:
    sites = payload.get("data", []) if isinstance(payload, dict) else payload
    return [site for site in sites if isinstance(site, dict)] if isinstance(sites, list) else []


def _discover_sites(settings: Settings) -> list[dict[str, Any]]:
    tls_ca = settings.ca_cert_path or ("system trust store" if settings.verify_tls else "verification disabled")
    if settings.api_mode == "local":
        api_kind = "local Network Integration"
        endpoint = "/proxy/network/integration/v1/sites"
    else:
        api_kind = "cloud Site Manager"
        endpoint = "/v1/sites"
    print("Verifying UniFi API connection:")
    print(f"  mode: {api_kind}")
    print(f"  base URL: {settings.api_base_url}")
    print(f"  endpoint: {endpoint}")
    print(f"  TLS: {'enabled' if settings.verify_tls else 'disabled'} ({tls_ca})")
    print(f"  API key: {'present' if settings.api_key else 'absent'}")

    async def operation():
        for attempt in range(5):
            client = UniFiClient(settings)
            try:
                return await client.list_sites()
            except UniFiError as exc:
                if not _looks_like_tls_failure(exc) or attempt == 4:
                    raise
                delay = 2**attempt
                print(f"  TLS reload in progress; retrying in {delay}s")
                await asyncio.sleep(delay)
            finally:
                await client.aclose()

    return _extract_sites(_run_async(operation()))


def _select_site(sites: list[dict[str, Any]]) -> str:
    if not sites:
        raise CliError("UniFi returned no visible sites")
    if len(sites) == 1:
        site_id = sites[0].get("siteId") or sites[0].get("id")
        if site_id:
            return str(site_id)
    print("Available sites:")
    for index, site in enumerate(sites, 1):
        print(f"  {index}. {site.get('name') or site.get('siteName') or site.get('siteId')}")
    selected = int(_prompt("Select site number"))
    if selected < 1 or selected > len(sites):
        raise CliError("invalid site selection")
    site_id = sites[selected - 1].get("siteId") or sites[selected - 1].get("id")
    if not site_id:
        raise CliError("selected site has no site ID")
    return str(site_id)


def _generate_local_certificates(config_path: Path) -> tuple[Path, Path, Path]:
    from scripts.generate_unifi_cert import (
        CertificateRequest,
        expected_files,
        generate_certificates,
        validate_request,
    )

    _ensure_private_config_dir(config_path.parent)
    output_dir = config_path.parent / "certificates"
    _ensure_private_config_dir(output_dir)
    domain = _prompt("Certificate DNS domain", "unifi.local")
    ip_address = _prompt("Certificate IP address", "192.168.0.1")
    organization = _prompt("Certificate organization (O)", "UniFi Observer")
    common_name = _prompt("Certificate common name (CN)", domain)
    request = CertificateRequest(domain, ip_address, organization, common_name, output_dir)
    validate_request(request)
    files = expected_files(request)
    existing = [path for path in files if path.exists()]
    if existing:
        print("Existing certificate material was found:")
        for path in existing:
            print(f"  - {path}")
        print("Recreating it will replace the existing certificate and may invalidate the certificate currently installed in UniFi.")
        choice = _prompt("Choose: replace, reuse, or cancel", "reuse").lower()
        if choice in {"reuse", "r", "reutilizar"}:
            required = (files[1], files[2], files[5])
            missing = [path for path in required if not path.exists()]
            if missing:
                raise CliError(f"cannot reuse existing certificate material; missing: {missing[0]}")
            if files[2].stat().st_mode & 0o077:
                raise CliError(f"private key must be private: {files[2]}")
            print("Reusing the existing certificate material; no certificate files will be deleted.")
        elif choice in {"replace", "p", "rehacer"}:
            print("WARNING: replacing the existing material will overwrite the files listed above.")
            confirmation = _prompt("Type REPLACE to confirm replacement")
            if confirmation != "REPLACE":
                raise CliError("certificate replacement cancelled; no files were changed")
            request = replace(request, force=True)
            files = generate_certificates(request)
        else:
            raise CliError("certificate configuration cancelled; no files were changed")
    else:
        files = generate_certificates(request)
    print("Certificate files ready:")
    for path in files:
        print(f"  - {path}")
    print(f"Certificate material directory: {output_dir}")
    return (
        output_dir / f"{domain}.fullchain.crt",
        output_dir / f"{domain}.key",
        output_dir / "unifi-local-ca.crt",
    )


def _certificate_command(config_path: Path) -> int:
    _generate_local_certificates(config_path)
    return 0


def _upload_local_certificate(
    settings: Settings,
    certificate_path: Path,
    private_key_path: Path,
) -> str | None:
    username = _prompt("UniFi Console administrator username")
    password = _prompt("UniFi Console administrator password", secret=True)
    certificate_pem = certificate_path.read_text(encoding="utf-8")
    private_key_pem = private_key_path.read_text(encoding="utf-8")

    async def request_two_factor() -> str:
        return _prompt("UniFi 2FA token", secret=True)

    async def operation() -> str | None:
        uploader = UniFiWebApiClient(settings.api_base_url, settings.timeout_seconds)
        try:
            bootstrap = UniFiConsoleBootstrap(uploader)
            return await bootstrap.run(
                username=username,
                password=password,
                certificate_name=certificate_path.name.removesuffix(".fullchain.crt"),
                certificate_pem=certificate_pem,
                private_key_pem=private_key_pem,
                request_two_factor=request_two_factor,
                generate_api_key=not bool(settings.api_key),
            )
        except CertificateUploadError as exc:
            raise CliError(f"automatic UniFi certificate upload failed: {exc}") from exc
        finally:
            await uploader.aclose()

    generated_api_key = _run_async(operation())
    print("api_key_created: " + ("true" if generated_api_key else "false"))
    print(f"api_key_length: {len(generated_api_key) if generated_api_key else 0}")
    print("Certificate uploaded and activated on UniFi Console.")
    if generated_api_key:
        print("UniFi API key generated and kept out of console output.")
    return generated_api_key


def _prepare_local_tls(settings: Settings, config_path: Path) -> Settings:
    verify = _prompt("Verify TLS connection on local mode? (recommended)", "yes")
    if verify.lower() not in {"y", "yes"}:
        print("TLS verification disabled for local mode. Use only on a trusted network.")
        return replace(settings, verify_tls=False, ca_cert_path=None)

    settings = replace(settings, verify_tls=True)
    generate = _prompt("Generate certificates for local verification with Unifi?", "yes")
    if generate.lower() in {"y", "yes"}:
        server_cert, private_key, ca_cert = _generate_local_certificates(config_path)
        automatic_upload = _prompt("Upload certificate automatically to UniFi Console? (recommended)", "yes")
        if automatic_upload.lower() in {"y", "yes"}:
            try:
                generated_api_key = _upload_local_certificate(settings, server_cert, private_key)
                return replace(
                    settings,
                    ca_cert_path=str(ca_cert),
                    api_key=generated_api_key or settings.api_key,
                )
            except CliError as exc:
                print(f"Automatic upload unavailable: {exc}")
                manual_fallback = _prompt("Continue with manual certificate upload?", "yes")
                if manual_fallback.lower() not in {"y", "yes"}:
                    raise
        print(f"  server certificate: {server_cert}")
        print(f"  private key: {private_key}")
        print(f"  CA certificate for Observer: {ca_cert}")
        _prompt("Upload the certificate and key to UniFi Console, then press Enter to verify the connection")
        if not settings.api_key:
            settings = replace(settings, api_key=_prompt("UniFi Network Integration API key", secret=True) or None)
        return replace(settings, ca_cert_path=str(ca_cert))

    _prompt("Upload or trust the existing certificate on UniFi Console, press Enter when done to verify the connection")
    if not settings.api_key:
        settings = replace(settings, api_key=_prompt("UniFi Network Integration API key", secret=True) or None)
    return settings


def _unit_path() -> Path:
    return Path("~/.config/systemd/user/unifi-observer.service").expanduser()


def _write_unit(config_path: Path) -> Path:
    path = _unit_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""[Unit]\nDescription=UniFi Observer MCP service\nAfter=network-online.target\n\n[Service]\nType=simple\nExecStart={shlex.quote(sys.executable)} -m unifi_observer.server\nEnvironmentFile={shlex.quote(str(config_path.expanduser()))}\nRestart=on-failure\nRestartSec=5\n\n[Install]\nWantedBy=default.target\n""",
        encoding="utf-8",
    )
    path.chmod(0o644)
    return path


def _systemctl(action: str) -> int:
    result = subprocess.run(["systemctl", "--user", action, "unifi-observer.service"], check=False)
    return result.returncode


def _service_command(action: str) -> int:
    if not _unit_path().exists():
        raise CliError("native service is not configured; run 'unifi-observer configure' first")
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
    return _systemctl(action)


def _looks_like_tls_failure(error: UniFiError) -> bool:
    message = str(error).lower()
    return any(
        marker in message
        for marker in (
            "certificate_verify_failed",
            "certificate verify failed",
            "hostname mismatch",
            "ssl: certificate",
        )
    )


def _configure(config_path: Path) -> int:
    settings = _prompt_settings()
    if settings.api_mode == "local":
        settings = _prepare_local_tls(settings, config_path)
    try:
        sites = _discover_sites(settings)
    except UniFiError as exc:
        if exc.status_code is not None:
            print(f"official_api_response: HTTP {exc.status_code}")
        else:
            print("official_api_response: connection_error")
        print(f"official_api_error: {exc}")
        if exc.status_code in {401, 403}:
            raise CliError(
                "UniFi official API rejected the API key (HTTP "
                f"{exc.status_code}). Verify that the key is present, valid, and has access "
                "to the selected console/site."
            ) from exc
        if _looks_like_tls_failure(exc):
            raise CliError(
                "TLS connection verification failed. Confirm that the UniFi Console "
                "has the generated certificate and that the CA path is trusted."
            ) from exc
        raise CliError(f"UniFi official API request failed: {exc}") from exc
    except RuntimeError as exc:
        if settings.api_mode == "local" and settings.verify_tls:
            raise CliError(
                "TLS connection verification failed. Confirm that the UniFi Console "
                "has the generated certificate and that the CA path is trusted."
            ) from exc
        raise
    site_id = _select_site(sites)
    settings = replace(settings, site_id=site_id, allowed_site_ids=(site_id,))
    write_env_file(config_path, _settings_to_values(settings))
    unit = _write_unit(config_path)
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
    print(f"Configuration written to {config_path}")
    print(f"Service unit written to {unit}")
    if settings.api_mode == "local" and settings.api_key:
        print(f"UniFi API key configured: [REDACTED]...{settings.api_key[-4:]}")

    if settings.api_mode == "local" and settings.verify_tls:
        print("TLS connection verified successfully.")
    print("Run 'unifi-observer start' when ready.")
    return 0


def _get_site(config_path: Path) -> int:
    settings = _settings_from_values(load_env_file(config_path)) if config_path.exists() else _prompt_settings()
    sites = _discover_sites(settings)
    print(json.dumps(sites, indent=2, ensure_ascii=False))
    return 0


def _uninstall(config_path: Path) -> int:
    if _prompt("Remove native service and configuration (certificates are preserved)", "no").lower() not in {"y", "yes"}:
        print("Cancelled.")
        return 0
    if _systemctl("is-active") == 0 and (_systemctl("stop") != 0 or _systemctl("is-active") == 0):
        raise CliError("could not stop the native service; configuration was preserved")
    if _unit_path().exists():
        if _systemctl("disable") != 0:
            raise CliError("could not disable the native service; configuration was preserved")
        _unit_path().unlink()
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
    if config_path.exists():
        config_path.unlink()
    print("Native service and configuration removed. Generated certificates were preserved.")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config_path = DEFAULT_CONFIG_PATH
    try:
        if args.command == "get-site":
            return _get_site(config_path)
        if args.command == "generate-certificate":
            return _certificate_command(config_path)
        if args.command == "configure":
            return _configure(config_path)
        if args.command in {"start", "stop", "restart", "status"}:
            return _service_command(args.command)
        if args.command == "uninstall":
            return _uninstall(config_path)
        raise CliError(f"unsupported command: {args.command}")
    except (CliError, OSError, ValueError, RuntimeError) as exc:
        print(f"unifi-observer: {exc}", file=sys.stderr)
        return 1
    except (EOFError, KeyboardInterrupt):
        print("unifi-observer: input cancelled", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
