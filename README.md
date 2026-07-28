# UniFi Observer

Read-only-first [Model Context Protocol](https://modelcontextprotocol.io/) server for querying UniFi Site Manager or a local UniFi Network application. It exposes UniFi inventory and health data to MCP clients such as Hermes and OpenClaw through Streamable HTTP.

## What it provides

- Sites and site details
- Infrastructure devices
- Connected clients
- Per-site health in local mode
- Native Linux installation with a `systemd --user` service
- Coolify/Docker deployment
- A safe self-update command for native installations

The current release is read-only. `UNIFI_ENABLE_WRITE=false` is the default and no write MCP tools are registered.

## Quick start: native Linux

Requirements: Linux, Python 3.11+, `systemd --user`, Git, and an interactive terminal.

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/vypdev/unifi-observer/master/install.sh)"
```

The wizard asks for credentials interactively, creates private configuration, optionally prepares local TLS certificates, and prepares—but does not start—the service.

```bash
unifi-observer start
unifi-observer status
```

For a non-interactive package installation without configuration:

```bash
UNIFI_OBSERVER_SKIP_CONFIGURE=1 \
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/vypdev/unifi-observer/master/install.sh)"
```

The native service is installed under `~/.local/share/unifi-observer`; its CLI link is `~/.local/bin/unifi-observer` and its private configuration is `~/.config/unifi-observer/config.env`.

## Native commands

```text
unifi-observer configure
unifi-observer start|stop|restart|status
unifi-observer update
unifi-observer generate-certificate
unifi-observer get-site
unifi-observer uninstall
```

`unifi-observer update` checks the latest commit on `master`. It does nothing when the installed commit matches; otherwise it installs the new revision, verifies the commit marker, restarts the user service, and verifies that systemd reports it active. It never rewrites `config.env` or generated certificate material.

## API modes

### Site Manager

```env
UNIFI_API_MODE=site-manager
UNIFI_API_BASE_URL=https://api.ui.com
UNIFI_API_KEY=<secret>
```

### Local Network API

```env
UNIFI_API_MODE=local
UNIFI_API_BASE_URL=https://<unifi-console-host>
UNIFI_API_KEY=<secret>
UNIFI_SITE_ID=<site-id>
UNIFI_VERIFY_TLS=true
UNIFI_CA_CERT_PATH=/path/to/local-ca.crt
```

In local mode, client and device list operations follow upstream pagination and return the complete collection. In Site Manager mode, unsupported operations fail explicitly rather than probing undocumented endpoints.

## MCP endpoint

The server exposes:

```text
GET  /healthz
GET  /readyz
POST /mcp
```

Native installations default to `127.0.0.1`. Container deployments must protect `/mcp` at the reverse proxy or private-network boundary before connecting Hermes or OpenClaw.

## Coolify / Docker

Create a Docker Compose application from this repository. Configure `UNIFI_API_KEY` as a Coolify secret and set the remaining variables through the runtime environment. Do not commit credentials. See [docs/deployment.md](docs/deployment.md).

## Documentation

Start with [docs/README.md](docs/README.md). It links to installation, configuration, operations, security, architecture, development, MCP integration, and the observed UniFi OS web-console contracts.

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[test,dev]'
.venv/bin/python -m pytest
.venv/bin/python -m ruff check src tests
.venv/bin/python -m mypy src
.venv/bin/python -m build
```

The repository uses Clean Architecture, typed boundaries, dependency injection, and explicit verification of upstream response shapes. See [docs/development.md](docs/development.md).

## Security

Never commit API keys, administrator credentials, MFA tokens, session cookies, private keys, or private network details. Keep TLS verification enabled in steady state. The local UniFi web-console adapter is a short-lived, firmware-dependent bootstrap mechanism; it is not a public administrator API proxy. See [docs/security.md](docs/security.md).

## License

See the repository license file when present.
