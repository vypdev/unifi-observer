# Architecture

## Runtime topology

```text
Hermes / OpenClaw
        │ Streamable HTTP /mcp
        ▼
unifi-observer ───────────────► UniFi Site Manager API
        │                         or local UniFi Network API
        ├── /healthz
        └── /readyz
```

The MCP transport is stateless at the HTTP layer. The current product exposes read-only tools.

## Clean Architecture

```text
presentation → application → domain
      ↑              ↑
infrastructure ──────┘
         composition wires the runtime
```

- `domain`: models, policies, and errors without transport or vendor dependencies.
- `application`: use cases and ports such as `UniFiGateway` and `UniFiWebConsolePort`.
- `infrastructure`: configuration, HTTP clients, TLS/certificate helpers, and system integrations.
- `presentation`: MCP tools, health routes, and terminal presentation.
- `composition`: production dependency wiring and process entry points.

## Two UniFi client boundaries

The official/read-only Network Integration client serves steady-state MCP operations. The typed UniFi OS web-console client is a short-lived bootstrap adapter for login/MFA, certificate management, and API-key creation. They must not be merged into one credential or endpoint boundary.

## Deployment adapters

Native Linux uses a user-owned virtual environment and `systemd --user`; Coolify uses the container image and reverse-proxy boundary. Both use the same application layers and environment contract. Native defaults bind to loopback; container defaults assume Coolify provides access control.

## Pagination guarantee

Infrastructure adapters consume all upstream pages for clients and devices, validate progress and metadata, and return a normalized complete collection. Presentation tools do not implement pagination themselves.
