# Delete certificate

## Purpose

Remove an older exact-name certificate after the replacement is active and verified.

## Request

```http
DELETE https://<console>/api/userCertificates/<certificate-id>
X-Csrf-Token: <csrf-token>
Cookie: TOKEN=[REDACTED]; JSESSIONID=[REDACTED]
```

## Response

```http
HTTP 204 No Content
```

Only delete IDs captured from the authenticated list response and owned by the configured server identity. Never delete the active certificate before a replacement has been activated and a normal TLS-verified request succeeds.
