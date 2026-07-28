# Security Policy

UniFi Observer is public and read-only-first.

- Never commit UniFi API keys, administrator credentials, MFA tokens, cookies, session tokens, private keys, or deployment secret exports.
- Keep `UNIFI_ENABLE_WRITE=false`; the current release registers no mutation tools.
- Protect `/mcp` at the reverse-proxy or private-network boundary.
- Keep `UNIFI_VERIFY_TLS=true` in steady state.
- Use `UNIFI_ALLOWED_SITE_IDS` to reduce the scope of read access.
- Treat the UniFi OS web-console adapter as a short-lived, firmware-dependent bootstrap mechanism—not as a public administrator API.

The complete operational security guidance is in [docs/security.md](docs/security.md). Before adding write tools, define separate capabilities, explicit tool allowlists, confirmation, audit records, recovery behavior, repeated-call tests, and deployment documentation.
