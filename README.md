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

In `local` mode, `unifi_list_devices` and `unifi_list_clients` automatically follow the upstream
pagination fields (`offset`, `limit`, `count`, `totalCount`) and merge every page into one
complete response. This prevents the MCP from silently exposing only the default first page.
If the console returns inconsistent pagination metadata, the request fails explicitly instead
of returning a partial inventory.

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

### One-line installation

On a Linux host with `systemd --user`, the supported bootstrap command is:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/vypdev/unifi-observer/master/install.sh)"
```

The installer downloads the selected repository revision over HTTPS, creates an
isolated user-owned virtual environment under `~/.local/share/unifi-observer`,
links the CLI at `~/.local/bin/unifi-observer`, and immediately starts the
interactive configuration wizard. It never accepts credentials as arguments.
If `python3` or the matching Python `venv` package is missing on Debian/Ubuntu,
the installer uses `apt-get` (through `sudo` when needed) to install them. It
requires Python 3.11 or newer; on other distributions it reports the missing
runtime/package instead of modifying an unsupported package manager.

Review `install.sh` before piping it to Bash in production. For an installation
without starting the wizard (for testing or image preparation only):

```bash
UNIFI_OBSERVER_SKIP_CONFIGURE=1 \
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/vypdev/unifi-observer/master/install.sh)"
```

```bash
unifi-observer get-site
unifi-observer generate-certificate
unifi-observer configure
unifi-observer start
unifi-observer stop
unifi-observer restart
unifi-observer status
unifi-observer update
unifi-observer uninstall
```

Commands prompt for required values rather than accepting credentials as command-line
arguments. `configure` interactively selects the API mode, prepares local TLS material when
requested, discovers the visible site ID, writes a private configuration file under
`~/.config/unifi-observer/`, and prepares a `systemd --user` service. In local mode it
asks:

```text
Verify TLS connection on local mode? (recommended)
Generate certificates for local verification with Unifi?
```

When certificates are generated, the wizard prints the exact server `.crt` path and
the CA path. By default it offers automatic upload through the local UniFi OS web-console
workflow. It asks interactively for the local UniFi administrator username and password.
If UniFi returns `api.err.Ubic2faTokenRequired` (HTTP 499), it asks for the one-time 2FA
token and resubmits the login. None of these credentials are stored in configuration or
logs. The upload sequence creates and activates the certificate through:

```text
POST /api/auth/login
POST /api/userCertificates
PUT  /api/userCertificates/{id}/status
```

The same authenticated session creates the local Network Integration API key through the
web-console endpoint `/proxy/users/api/v2/user/{user_id}/keys`. The key is returned only once
in `data.full_api_key`, stored in the private configuration file, and never printed. The
permissions returned by current UniFi OS versions may be broader than
the Observer's read-only behavior; use a dedicated local UniFi account where possible and
review/revoke the generated key from the console when no longer needed.

The wizard asks for a stable server identifier, defaulting to the local hostname. Local
resources are namespaced with that identifier:

```text
API key:     unifi-observer-ai-core
certificate: unifi.local-ai-core
files:       unifi.local-ai-core.fullchain.crt
             unifi.local-ai-core.key
             unifi-local-ca-ai-core.crt
```

The certificate SAN remains `unifi.local` (and the configured console IP), so the identifier
does not change the hostname used for TLS verification. On a later configuration of the same
server, the authenticated bootstrap lists resources, matches the exact server names, creates
and activates replacements, then deletes only the previous matching API key and certificate.
The final private configuration also records the non-secret `UNIFI_API_KEY_ID` and
`UNIFI_CERTIFICATE_ID` values.

The internal web-console integration is documented in
[`docs/unifi-web-console-api.md`](docs/unifi-web-console-api.md). It records observed
request/response contracts without retaining session cookies, CSRF tokens, API keys, or
private keys, and includes the capture template for future web calls.

It uses disabled certificate verification only for the local bootstrap session because the
factory UniFi certificate is not valid for the local hostname/IP. After activation, the
bootstrap session is closed and the normal client verifies the connection with the generated
CA and `UNIFI_VERIFY_TLS=true`. The verification waits briefly when the console is reloading
its HTTPS service after certificate activation. The web-console endpoints are
internal/version-dependent;
if the upload is rejected or unavailable, configuration stops without persisting settings
and the wizard can fall back to the manual upload path:

```text
Upload this certificate to UniFi Console, press Enter when done to verify the connection
```

Only after a real TLS-verified site discovery succeeds does it persist the final
configuration and prepare the service. The generated setting `UNIFI_CA_CERT_PATH` keeps
verification enabled without requiring a system-wide trust-store modification. Installing the
CA globally is optional and only needed if other applications on the host must trust the local
console certificate.
The service is not started automatically; run `unifi-observer start` after reviewing
the generated unit.

To update an existing native installation, run:

```bash
unifi-observer update
```

`update` queries the latest commit on `master`, compares it with the commit marker recorded
by the installer, and exits without touching the service when they match. When a newer commit
exists, it downloads that revision into a temporary checkout, runs the installation step with
configuration skipped, verifies the installed commit marker, restarts the user service, and
checks that systemd reports it as active. The update never changes `config.env` or generated
certificate material. `UNIFI_OBSERVER_REPOSITORY_URL`, `UNIFI_OBSERVER_REF`,
`UNIFI_OBSERVER_INSTALL_DIR`, and `UNIFI_OBSERVER_BIN_DIR` can override the defaults for
controlled deployments; the repository URL must use HTTPS.

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

When `unifi-observer configure` detects existing material under
`~/.config/unifi-observer/certificates`, it shows the files and offers:

- **reuse**: keeps every existing file and continues with the existing certificate/key upload;
- **replace**: warns that the existing material will be overwritten and requires typing
  `REPLACE` before using the generator's atomic replacement path;
- **cancel**: exits without deleting or changing the certificate material.

For a trusted local deployment:

1. Upload `<domain>-<server-id>.fullchain.crt` and `<domain>-<server-id>.key` to the UniFi console.
2. Configure `UNIFI_CA_CERT_PATH` with `unifi-local-ca-<server-id>.crt`. Installing the CA in the system
   trust store is optional; on Debian/Ubuntu, use:
   ```bash
   sudo cp unifi-local-ca-<server-id>.crt /usr/local/share/ca-certificates/unifi-local-ca-<server-id>.crt
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

Use the Streamable HTTP endpoint at `/mcp`:

```text
https://<coolify-host>/mcp
```

Do not configure write-capable tools until the read-only deployment has passed transport, persistence/session, tool listing, and repeated-call tests from both Hermes and OpenClaw.
