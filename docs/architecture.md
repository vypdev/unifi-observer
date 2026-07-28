# Architecture

## Runtime

```text
Hermes ───────┐
              │  Streamable HTTP /mcp
OpenClaw ─────┤──────────────┐
              │              │
              ▼              ▼
        unifi-observer  /healthz /readyz
              │
              ▼
      UniFi Site Manager API
      or local UniFi Network API
```

The MCP server is stateless at the HTTP transport layer. It does not rely on one long-lived SSE connection or a client-specific session surviving between tool calls.

## Modes

| Mode | Purpose | Write tools |
|---|---|---:|
| `read-only` | inventory, clients, devices, health, site details | disabled |
| `operator` | future bounded reversible actions | explicit opt-in |
| `admin` | future disruptive administration | separate approval and deployment |

The repository currently implements only `read-only`.

## Internal Clean Architecture

The runtime is split into explicit dependency boundaries:

```text
presentation  →  application  →  domain
      ↑              ↑
infrastructure ──────┘
             composition wires all layers
```

- `domain`: application errors and policies with no transport or vendor dependencies;
- `application`: read-only use cases and the `UniFiGateway` port;
- `infrastructure`: environment configuration, the read-only `httpx` UniFi adapter, and
  the isolated UniFi OS web-console certificate bootstrap adapter;
- `presentation`: MCP tools and HTTP health/readiness routes;
- `composition`: production dependency wiring and process entry point.

The web-console bootstrap is exposed internally through a typed client boundary:

```text
application/ports.py
    UniFiWebConsolePort

infrastructure/unifi_web_api_client.py
    UniFiWebApiClient

domain/unifi_web_api_models.py
    LoginRequest / LoginResponse
    TwoFactorRequest / LoginSuccessResponse
    UploadCertificateRequest / UploadCertificateResponse
    ActivateCertificateRequest / ActivateCertificateResponse
    CreateApiKeyRequest / CreateApiKeyResponse
```

The DTOs are transport contracts rather than untyped dictionaries. Secret-bearing fields
are excluded from representations, while unknown upstream fields remain available through
`raw` for forward compatibility. This package boundary is intentionally suitable for a
future extraction into a standalone `unifi-web-api` repository.


```text
MCP client ──/mcp──> unifi-observer ──> UniFi Network API
                                      └─> official/read-only operations

configure CLI ──> application bootstrap port
                       └─> infrastructure UniFi OS web-console adapter
                           └─> short-lived login/MFA/upload/API-key session
```

`unifi-observer` is not a public proxy for UniFi's administrator login API. It consumes
selected internal web-console calls only during local bootstrap, keeps administrator
credentials and session material in memory, closes the session, and then uses the official
Network Integration API key for normal operation. The internal endpoint contract is
firmware-dependent and must never be exposed as an unauthenticated or general-purpose
remote API.

The `UniFiWebConsolePort` defines the application boundary for this bootstrap workflow. The
`UniFiConsoleBootstrap` use case owns the sequence and receives the web-console adapter by
injection. The CLI remains an outer composition adapter: it collects input and supplies the
interactive MFA callback, but it does not call the individual web API operations directly.

The installer is also an outer adapter boundary:
- `install.sh` performs HTTPS repository bootstrap into a temporary checkout;
- `scripts/setup.sh` creates the user-owned virtual environment and CLI link;
- setup launches `unifi-observer configure` only after the package is installed;
- credentials are collected by the CLI, never by shell arguments or installer flags.

The MCP adapter receives use cases through dependency injection. It must not construct
HTTP clients or read environment variables during module import. This keeps use cases
unit-testable and allows future CLI, HTTP, or OpenClaw adapters without changing the
application layer.

## API modes

- `site-manager`: official cloud API, normally `https://api.ui.com` and `X-API-Key`.
- `local`: local UniFi Network API, with a configurable console URL and site ID.

The legacy value `network-integration` is accepted as a compatibility alias and is
normalized to `local` at configuration boundaries.

The upstream contract must be checked against the installed UniFi version before production deployment. The client deliberately returns bounded errors instead of dumping upstream response bodies into model context.

The current Site Manager contract covers sites and devices. Client inventory and
per-site health use the local mode; in `site-manager` those tools return an explicit
unsupported-operation error instead of probing undocumented endpoints.

## Transport decision

The previous server exposed legacy `/sse` and returned an endpoint event, but did not deliver the JSON-RPC response after `initialize`. This implementation uses MCP Streamable HTTP at `/mcp` with `stateless_http=true` and JSON responses. Contract tests cover tool registration and invocation through the presentation adapter; the release smoke-test procedure covers HTTP initialization and repeated calls.

## Deployment boundary

Coolify should provide:

- runtime environment variables for credentials;
- HTTPS and access control for `/mcp`;
- private networking to the UniFi controller when using local API mode;
- health checks against `/healthz`;
- no public database or auxiliary service.

Native deployment provides the same application through `unifi-observer.service`:

- the one-line installer installs into `~/.local/share/unifi-observer` and links
  `~/.local/bin/unifi-observer`;
- `unifi-observer configure` prepares private configuration and the user unit;
- local configuration can generate a CA/server certificate pair and offers an automatic
  UniFi OS web-console upload; username/password and an on-demand 2FA token remain
  in-memory only;
- the upload adapter uses the internal, firmware-dependent web-console endpoints only
  for bootstrap and falls back to manual upload when unavailable;
- the same session can create a Network Integration API key; current consoles may return
  broad account permissions, so the generated key must not be described as read-only;
- after activation, the client performs TLS-verified site discovery before persistence;
- `UNIFI_CA_CERT_PATH` lets the HTTP adapter trust the generated CA without disabling
  TLS verification or changing the system trust store;
- `unifi-observer start|stop|restart|status` delegates lifecycle operations to
  `systemctl --user`;
- `unifi-observer uninstall` removes the unit and configuration but preserves generated
  certificate material for deliberate cleanup.
