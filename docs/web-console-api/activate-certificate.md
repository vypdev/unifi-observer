# Activate certificate

## Purpose

Make the uploaded certificate the active UniFi console certificate.

## Request

```http
PUT https://<console>/api/userCertificates/<certificate-id>/status
X-Csrf-Token: <csrf-token>
Cookie: TOKEN=[REDACTED]; JSESSIONID=[REDACTED]

{"active":true}
```

The adapter uses the typed `ActivateCertificateRequest` and validates the response before proceeding.

## Operational note

UniFi may briefly continue serving the old certificate while its HTTPS service reloads. The bootstrap flow retries the subsequent CA-verified Network Integration request with bounded delays. It must never treat a temporary reload as permission to disable steady-state TLS verification.
