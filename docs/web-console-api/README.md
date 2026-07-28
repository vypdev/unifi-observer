# UniFi OS web-console API contracts

These documents record calls observed in the UniFi OS web console during local bootstrap. They are internal, authenticated, firmware-dependent integration contracts—not a public or version-stable UniFi API.

## Rules

- Use only during the short-lived native bootstrap flow.
- Keep passwords, MFA tokens, session cookies, CSRF values, private keys, and full API keys in memory only.
- Use placeholders in requests and responses.
- Keep exact resource IDs and server names scoped to the configured server identity.
- Verify the replacement certificate before deleting an old active resource.

## Operations

1. [Login](login.md)
2. [Verify 2FA](verify-2fa.md)
3. [List API keys](list-api-keys.md)
4. [Create API key](create-api-key.md)
5. [Delete API key](delete-api-key.md)
6. [List certificates](list-certificates.md)
7. [Upload certificate](upload-certificate.md)
8. [Activate certificate](activate-certificate.md)
9. [Delete certificate](delete-certificate.md)

## Client boundary

`domain/unifi_web_api_models.py` contains typed DTOs, `infrastructure/unifi_web_api_client.py` implements transport, `application/ports.py` exposes `UniFiWebConsolePort`, and `application/bootstrap.py` orchestrates the flow. This client is separate from the official Network Integration client used by normal MCP calls.

Capture future calls with: operation, date, UniFi OS version, Network application version, method, path, status, required non-secret headers, redacted body/response, prerequisites, side effects, rollback, and compatibility notes.
