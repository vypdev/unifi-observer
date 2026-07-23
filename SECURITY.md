# Security Policy

## Default posture

This project is public and is intentionally read-only-first.

- Never commit UniFi API keys, passwords, cookies, session tokens, controller URLs containing credentials, or Coolify environment exports.
- Keep `UNIFI_ENABLE_WRITE=false`.
- The initial release registers no mutation tools.
- Protect the deployed MCP endpoint at the reverse proxy or network layer.
- Prefer HTTPS for both the public MCP endpoint and the UniFi upstream.
- Keep `UNIFI_VERIFY_TLS=true`.
- Use `UNIFI_ALLOWED_SITE_IDS` to reduce the blast radius of read access.

## Future write mode

Write tools must not be enabled by changing one environment variable alone. Before adding them, the project must define:

1. a separate capability/profile;
2. explicit tool-level allowlists;
3. confirmation for disruptive operations;
4. audit records without secrets;
5. rollback or recovery behavior;
6. fresh Hermes and OpenClaw tests for repeated calls;
7. a documented Coolify deployment procedure.
