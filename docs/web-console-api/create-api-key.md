# Create API key

## Purpose

Create the steady-state Network Integration credential after certificate preparation.

## Request

```http
POST https://<console>/proxy/users/api/v2/user/<user-id>/keys
Content-Type: text/plain;charset=UTF-8
X-Csrf-Token: <csrf-token>
Cookie: TOKEN=[REDACTED]; JSESSIONID=[REDACTED]

{"description":"UniFi Observer local integration key","name":"unifi-observer-<server-id>"}
```

The observed browser body is JSON despite the `text/plain` content type.

## Response

```json
{"code":1,"codeS":"SUCCESS","data":{"id":"<key-id>","name":"<name>","full_api_key":"[REDACTED]","permissions":{},"scopes":[]}}
```

Require a non-empty `data.full_api_key`, keep it in memory, verify the resulting connection, and persist it only at the final configuration transaction boundary. Never print or document the full value. Current consoles may grant broad account permissions; read-only application behavior does not reduce key privileges.
