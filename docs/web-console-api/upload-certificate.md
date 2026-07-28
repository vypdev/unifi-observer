# Upload certificate

## Purpose

Upload the generated server certificate and matching private key to the authenticated console.

## Request

The current adapter calls the observed `POST /api/userCertificates` operation with the certificate name and PEM material. The exact wire fields are represented by `UploadCertificateRequest`; private material is never logged.

```text
POST /api/userCertificates
certificate: <PEM certificate>
privateKey: [REDACTED PEM private key]
name: <domain>-<server-id>
```

## Response

The typed response must contain a successful HTTP status and a non-empty certificate ID. Malformed or unsuccessful responses raise a certificate-upload error and stop configuration before persistence.

The uploaded certificate is not considered active until [Activate certificate](activate-certificate.md) succeeds and a normal CA-verified request completes.
