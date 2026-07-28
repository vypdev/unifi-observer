# List certificates

## Purpose

List uploaded certificate metadata so bootstrap can identify an exact server-owned certificate.

## Request

```http
GET https://<console>/api/userCertificates
X-Csrf-Token: <csrf-token>
Cookie: TOKEN=[REDACTED]; JSESSIONID=[REDACTED]
```

## Response

```json
[{"id":"<certificate-id>","name":"<name>","version":3,"subject":{"O":"<organization>","CN":"<common-name>"},"issuer":{"O":"<organization>","CN":"<issuer>"},"subject_alt_name":{"DNS":["<dns>"],"IP Address":["<ip>"]},"valid_from":"<timestamp>","valid_to":"<timestamp>","source":"uploaded","active":true}]
```

Private key material is not returned and must never be inferred from metadata. Match exact certificate names such as `<domain>-<server-id>`.
