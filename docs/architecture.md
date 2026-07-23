# Architecture

## Runtime

```text
Hermes ───────┐
              │  Streamable HTTP /mcp
OpenClaw ─────┤──────────────┐
              │              │
              ▼              ▼
        unifi-mcp-coolify  /healthz /readyz
              │
              ▼
      UniFi Site Manager API
      or Network Integration API
```

The MCP server is stateless at the HTTP transport layer. It does not rely on one long-lived SSE connection or a client-specific session surviving between tool calls.

## Modes

| Mode | Purpose | Write tools |
|---|---|---:|
| `read-only` | inventory, clients, devices, health, site details | disabled |
| `operator` | future bounded reversible actions | explicit opt-in |
| `admin` | future disruptive administration | separate approval and deployment |

The repository currently implements only `read-only`.

## API modes

- `site-manager`: official cloud API, normally `https://api.ui.com` and `X-API-Key`.
- `network-integration`: local UniFi console integration API, with a configurable console URL and site ID.

The upstream contract must be checked against the installed UniFi version before production deployment. The client deliberately returns bounded errors instead of dumping upstream response bodies into model context.

## Transport decision

The previous server exposed legacy `/sse` and returned an endpoint event, but did not deliver the JSON-RPC response after `initialize`. This implementation uses MCP Streamable HTTP at `/mcp` with `stateless_http=true` and JSON responses. Local smoke tests verified initialization, tool listing, and repeated calls.

## Deployment boundary

Coolify should provide:

- runtime environment variables for credentials;
- HTTPS and access control for `/mcp`;
- private networking to the UniFi controller when using local API mode;
- health checks against `/healthz`;
- no public database or auxiliary service.
