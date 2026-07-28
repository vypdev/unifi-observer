# Security

## Credential boundaries

`UNIFI_API_KEY` is the credential used by UniFi Observer to query UniFi. It is not an MCP client credential and must never be shared with Hermes, OpenClaw, or committed to Git. Native configuration is private and container secrets come from the deployment secret store.

Administrator passwords, MFA tokens, session cookies, CSRF tokens, private keys, and full API keys are memory-only during local web-console bootstrap. Examples and logs use placeholders or `[REDACTED]`.

## Network boundary

The native service binds to `127.0.0.1` by default. The current MCP endpoint does not implement bearer authentication itself, so remote access requires a protected reverse proxy or private network. Coolify deployments must not publish an unprotected `/mcp` endpoint.

## TLS

Keep `UNIFI_VERIFY_TLS=true` in steady state. Local bootstrap may temporarily use an unverified session only to reach a console whose factory certificate does not match its hostname/IP. After certificate activation, the client closes that session and verifies with the configured CA.

## Web-console adapter

The internal UniFi OS web-console calls are observed, firmware-dependent contracts used only during setup. UniFi Observer is not a public proxy for administrator login, MFA, certificate management, or API-key management. See the per-operation contracts in [web-console-api](web-console-api/README.md).

## Resource lifecycle

Server-specific names scope replacement of API keys and certificates. Bootstrap creates and verifies replacements before deleting exact-name resources. Never delete an active console certificate unless a replacement has been activated and verified.

## Repository hygiene

Before committing, check for credentials, generated certificates, private network identifiers, build output, caches, and temporary files. Use placeholders in tests and documentation.
