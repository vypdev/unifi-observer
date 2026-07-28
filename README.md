# UniFi Observer

Read-only-first UniFi Observer service with a Model Context Protocol (MCP) adapter for UniFi Site Manager or a local UniFi console.

The service is designed for deployment in Coolify and consumption by Hermes and OpenClaw through **Streamable HTTP**. It does not expose write tools in the initial release. Network modifications remain disabled by default and will require a separate, explicitly reviewed capability.

## Security model

- Public repository; no credentials or private network details belong in Git.
- Configure credentials only as Coolify runtime environment variables or an external secret store.
- `UNIFI_ENABLE_WRITE=false` is the default and write tools are not registered in this release.
- Restrict access to the MCP endpoint at the reverse proxy/network layer.
- Use `UNIFI_ALLOWED_SITE_IDS` to limit site scope.
- Keep `UNIFI_VERIFY_TLS=true` except during a controlled local diagnosis.

## Supported upstream modes

### UniFi Site Manager API

```env
UNIFI_API_MODE=site-manager
UNIFI_API_BASE_URL=https://api.ui.com
UNIFI_API_KEY=[REDACTED]
```

### Local UniFi Network API

```env
UNIFI_API_MODE=local
UNIFI_API_BASE_URL=https://<unifi-console>
UNIFI_API_KEY=[REDACTED]
UNIFI_SITE_ID=<site-id>
```

The exact API paths are kept in the client and can be tested without exposing the key. Consult the API documentation for the installed UniFi version before enabling production use.

`network-integration` remains accepted as a backward-compatible alias for `local`,
but new deployments should use `local`.

`site-manager` currently provides sites, devices, and site details derived from the
sites response. The `unifi_list_clients` and `unifi_get_health` tools require `local`
mode because those operations are not part of the current Site Manager API contract.

## Local development

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[test]'
.venv/bin/pytest
set -a; . ./.env; set +a
UNIFI_API_BASE_URL=https://api.ui.com \
  .venv/bin/python -m unifi_observer.server
```

The application reads configuration from the process environment; it does not load
`.env` files itself. The `set -a` step above is for local development only. Coolify
should inject the variables through its environment/secret configuration.

## Native interactive CLI

The product CLI and native service are named `unifi-observer`.

```bash
unifi-observer get-site
unifi-observer generate-certificate
unifi-observer configure
unifi-observer start
unifi-observer stop
unifi-observer restart
unifi-observer status
unifi-observer uninstall
```

Commands prompt for required values rather than accepting credentials as command-line
arguments. `configure` interactively selects the API mode, prepares local TLS material
when needed, discovers the visible site ID, writes a private configuration file under
`~/.config/unifi-observer/`, and prepares a `systemd --user` service. It does not start
the service automatically; run `unifi-observer start` after completing any UniFi
certificate upload and CA trust steps.

The native service and Coolify deployment use the same MCP application and environment
contract. Coolify remains the recommended container deployment path; the native CLI is
an alternative for hosts where systemd user services are preferred.

## Local UniFi TLS certificate helper

For a local UniFi console that uses a self-issued certificate, the repository includes
an OpenSSL-based helper that creates a local CA and a server certificate containing both
the DNS name and IP address as Subject Alternative Names (SANs):

```bash
./scripts/generate_unifi_cert.py \
  --domain unifi.local \
  --ip 192.168.0.1 \
  --organization "Efra Home Lab" \
  --common-name unifi.local \
  --output-dir ./unifi-certs
```

Omit the input options to be prompted interactively. For unattended use, pass all four
identity options together with `--non-interactive`. The helper requires the `openssl`
executable on `PATH`. It generates private keys, CA/server certificates, a CSR, and a
full-chain certificate. It does not overwrite existing files unless `--force` is
passed, applies restrictive permissions to private keys, and prints the next deployment
steps without printing key material.

For a trusted local deployment:

1. Upload `<domain>.fullchain.crt` and `<domain>.key` to the UniFi console.
2. Install `unifi-local-ca.crt`—the CA, not the server certificate—in the trust store of the MCP host. On Debian/Ubuntu:
   ```bash
   sudo cp unifi-local-ca.crt /usr/local/share/ca-certificates/unifi-local-ca.crt
   sudo update-ca-certificates
   ```
3. Resolve the domain to the console IP on the MCP host.
4. Keep `UNIFI_VERIFY_TLS=true` and use the generated domain in `UNIFI_API_BASE_URL`.

Never commit the generated directory or private keys.

For the full quality gate, install the development tools and run:

```bash
.venv/bin/pip install -e '.[test,dev]'
.venv/bin/pytest
.venv/bin/ruff check src tests
.venv/bin/mypy src
.venv/bin/python -m build
```

The server listens on port `8000` by default:

```text
GET  /healthz
GET  /readyz
POST /mcp       # Streamable HTTP MCP endpoint
```

## Coolify

Create a Docker Compose application from this repository. The Compose file declares
all runtime variables with safe defaults, so Coolify can pre-populate them when the
repository is imported. Set `UNIFI_API_KEY` explicitly as a Coolify secret; it has no
committed default. Do not commit actual values. Keep the application private to the
trusted network or protect it with an authenticated reverse proxy before adding it to
Hermes or OpenClaw.

## MCP client configuration

Use the Streamable HTTP endpoint, not the legacy `/sse` endpoint:

```text
https://<coolify-host>/mcp
```

Do not configure write-capable tools until the read-only deployment has passed transport, persistence/session, tool listing, and repeated-call tests from both Hermes and OpenClaw.
