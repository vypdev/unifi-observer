# Verify 2FA

## Purpose

Complete the MFA challenge returned by the first login request.

## Request

The browser repeats the same login route on the same session-aware HTTP client:

```http
POST https://<console>/api/auth/login
Content-Type: application/json

{"username":"<username>","password":"[REDACTED]","token":"<one-time-code>","rememberMe":false}
```

## Response

```http
HTTP 200 OK
X-Csrf-Token: <csrf-token>
X-Updated-Csrf-Token: <csrf-token>
Set-Cookie: TOKEN=[REDACTED]
```

The adapter returns typed session credentials and authenticated user identity. It must not persist the MFA token, challenge cookie, password, or complete profile.

## Failure

A repeated MFA challenge, `401`, `403`, timeout, or malformed success response is an authentication failure; do not proceed to certificate or API-key operations.
