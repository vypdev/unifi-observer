# Documentation

This directory contains the operational and technical documentation for UniFi Observer.

## Start here

- [Project README](../README.md) — short product overview and quick start.
- [Configuration](configuration.md) — environment variables, API modes, and validation.
- [Deployment](deployment.md) — native systemd and Coolify/Docker deployment.
- [Operations](operations.md) — lifecycle, updates, health checks, and troubleshooting.
- [Security](security.md) — secrets, TLS, network boundaries, and web-console bootstrap.
- [MCP integration](mcp.md) — endpoint and tool contract for Hermes/OpenClaw.
- [Architecture](architecture.md) — runtime topology and Clean Architecture boundaries.
- [Development](development.md) — local setup, tests, quality gates, and contribution rules.

## Observed UniFi OS web-console contracts

The web-console integration is an internal, firmware-dependent setup adapter—not a public UniFi API. Each operation has its own contract document:

- [Web-console API index](web-console-api/README.md)
- [Login](web-console-api/login.md)
- [Verify 2FA](web-console-api/verify-2fa.md)
- [List API keys](web-console-api/list-api-keys.md)
- [Create API key](web-console-api/create-api-key.md)
- [Delete API key](web-console-api/delete-api-key.md)
- [List certificates](web-console-api/list-certificates.md)
- [Upload certificate](web-console-api/upload-certificate.md)
- [Activate certificate](web-console-api/activate-certificate.md)
- [Delete certificate](web-console-api/delete-certificate.md)

All examples use placeholders. Never add cookies, CSRF values, administrator credentials, MFA values, private keys, or complete API keys to documentation.
