# List API keys

## Purpose

List API-key metadata belonging to the authenticated UniFi user so bootstrap can find an exact server-owned resource.

## Request

```http
GET https://<console>/proxy/users/api/v2/user/<user-id>/keys
X-Csrf-Token: <csrf-token>
Cookie: TOKEN=[REDACTED]; JSESSIONID=[REDACTED]
```

## Response

```json
{"code":1,"codeS":"SUCCESS","data":[{"id":"<key-id>","name":"<name>","masked_api_key":"<masked>","description":"<description>","created_at":"<timestamp>","updated_at":"<timestamp>","permissions":{},"key_permissions":[],"scopes":[]}]}
```

`masked_api_key` is display metadata, never a usable credential. Match exact names such as `unifi-observer-<server-id>` and the authenticated user; never perform a partial or global deletion search.
