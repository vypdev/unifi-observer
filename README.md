# UniFi MCP Coolify

Read-only-first Model Context Protocol (MCP) server for UniFi Site Manager or the UniFi Network Integration API.

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

### UniFi Network Integration API

```env
UNIFI_API_MODE=network-integration
UNIFI_API_BASE_URL=https://<unifi-console>
UNIFI_API_KEY=[REDACTED]
UNIFI_SITE_ID=<site-id>
```

The exact API paths are kept in the client and can be tested without exposing the key. Consult the API documentation for the installed UniFi version before enabling production use.

## Local development

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[test]'
.venv/bin/pytest
UNIFI_API_BASE_URL=https://api.ui.com \
  .venv/bin/unifi-mcp
```

The server listens on port `8000` by default:

```text
GET  /healthz
GET  /readyz
POST /mcp       # Streamable HTTP MCP endpoint
```

## Coolify

Create a Docker Compose application from this repository and provide the variables in `.env.example` through Coolify's environment settings. Do not commit the actual values. Keep the application private to the trusted network or protect it with an authenticated reverse proxy before adding it to Hermes or OpenClaw.

## MCP client configuration

Use the Streamable HTTP endpoint, not the legacy `/sse` endpoint:

```text
https://<coolify-host>/mcp
```

Do not configure write-capable tools until the read-only deployment has passed transport, persistence/session, tool listing, and repeated-call tests from both Hermes and OpenClaw.
