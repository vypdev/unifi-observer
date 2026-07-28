# Login

## Purpose

Authenticate an administrator to the local UniFi OS web console and obtain temporary session context.

## Request

```http
POST https://<console>/api/auth/login
Content-Type: application/json

{"username":"<username>","password":"[REDACTED]","token":"","rememberMe":false}
```

The first request deliberately sends an empty `token`. Do not guess an MFA value or add undocumented cookies.

## Responses

- `200 OK`: authenticated session; the response headers provide session/CSRF material.
- `499` with `MFA_AUTH_REQUIRED` or `api.err.Ubic2faTokenRequired`: typed MFA challenge; continue with [Verify 2FA](verify-2fa.md).
- `401`: credentials or local-account authorization rejected.
- `403`: account lacks permission.
- timeout/DNS/TLS: console could not be reached.

## Security

Passwords, response profiles, `TOKEN`, `JSESSIONID`, CSRF values, and challenge cookies are temporary secrets. The adapter keeps only the fields needed for subsequent operations and closes the session in all paths.
