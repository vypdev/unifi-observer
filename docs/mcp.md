# MCP integration

UniFi Observer exposes a Streamable HTTP MCP endpoint at `/mcp`.

## Transport

```text
POST https://<observer-host>/mcp
```

The server uses stateless HTTP transport and JSON responses. It also exposes:

```text
GET /healthz
GET /readyz
```

Protect the endpoint at the network or reverse-proxy boundary. The current service does not expose application-level bearer authentication.

## Read-only tools

| Tool | Description | Availability |
|---|---|---|
| `unifi_list_sites` | List visible sites. | Site Manager and local mode where supported. |
| `unifi_get_site` | Get one allowed site. | Site Manager and local mode where supported. |
| `unifi_get_health` | Return gateway/AP CPU, memory, uptime, uplink and radio statistics from each device's latest statistics endpoint. | Local mode. |
| `unifi_list_devices` | Return the complete paginated device collection. | Local mode and supported Site Manager contract. |
| `unifi_list_clients` | Return the complete paginated client collection. | Local mode. |

Unsupported operations return explicit errors. The adapter does not silently return the first upstream page as a complete inventory.

## Hermes/OpenClaw

Configure the MCP server URL in the client-facing MCP configuration. Do not give the client `UNIFI_API_KEY`; that key stays inside UniFi Observer. After enabling tools in Hermes, create a new session so tool discovery is refreshed.

## Safety contract

The current release registers no write tools. `UNIFI_ENABLE_WRITE=false` remains the default and is not a substitute for network access control.
