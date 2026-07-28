# Delete API key

## Purpose

Remove an older exact-name API key after its replacement has been created and verified.

## Request

```http
DELETE https://<console>/proxy/users/api/v2/keys/<key-id>
X-Csrf-Token: <csrf-token>
Cookie: TOKEN=[REDACTED]; JSESSIONID=[REDACTED]
```

## Response

```http
HTTP 200 OK
```

```json
{"code":1,"codeS":"SUCCESS","data":"success"}
```

Deletion accepts only a captured resource ID belonging to the configured server identity. The full key is never needed for deletion.
