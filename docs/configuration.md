# Configuration

UniFi Observer reads configuration from the process environment. The native CLI writes a private `config.env` for the systemd user service; the container deployment receives values from Coolify or Docker Compose.

## Core variables

| Variable | Default | Description |
|---|---|---|
| `UNIFI_API_MODE` | `site-manager` | `site-manager` or `local`. |
| `UNIFI_API_BASE_URL` | `https://api.ui.com` | UniFi API origin. |
| `UNIFI_API_KEY` | empty | Credential used by the steady-state UniFi client. |
| `UNIFI_SITE_ID` | empty | Required for local mode operations that need a site. |
| `UNIFI_ALLOWED_SITE_IDS` | empty | Comma-separated allow-list of site IDs. |
| `UNIFI_VERIFY_TLS` | `true` | Keep enabled outside controlled diagnosis. |
| `UNIFI_CA_CERT_PATH` | empty | Optional CA used for local UniFi TLS verification. |
| `UNIFI_TIMEOUT_SECONDS` | `15` | Bounded upstream request timeout. |
| `UNIFI_ENABLE_WRITE` | `false` | Write tools remain unavailable in the current release. |
| `MCP_HOST` | `127.0.0.1` native / `0.0.0.0` Compose | Bind address. |
| `MCP_PORT` | `8000` | HTTP port. |

## Native-only metadata

The wizard also persists non-secret resource metadata:

- `UNIFI_SERVER_ID`
- `UNIFI_API_KEY_ID`
- `UNIFI_CERTIFICATE_ID`

The full UniFi API key is stored only in the private native configuration file and is never required by Hermes/OpenClaw. MCP clients authenticate to the MCP boundary, not to UniFi directly.

## Local TLS

When local TLS is enabled, the wizard can generate a private CA and server certificate with DNS and IP SANs. `UNIFI_CA_CERT_PATH` lets the client trust that CA without modifying the system trust store. The generated private key directory is kept private.

The certificate upload flow may use a temporary unverified web-console session because the factory certificate is not valid for the configured hostname/IP. The steady-state API client always returns to CA-verified TLS.

## Validation rules

- `UNIFI_API_MODE` must be supported.
- URLs must use the expected HTTP(S) scheme.
- Timeouts and ports must be valid positive values.
- Private native configuration directories must not be group/world accessible.
- Credentials must not contain newlines when serialized to `config.env`.
