# UniFi OS Web Console Integration API

## Status and scope

This document records HTTP calls observed in the UniFi OS web console while configuring a local UniFi Console. It is an **observed internal integration contract**, not a public or version-stable UniFi API.

The documented call was captured from a UniFi Console reachable at `192.168.0.1` on 2026-07-28. The exact UniFi OS and Network application versions were not captured with the request and must be recorded for every future compatibility report.

The integration is implemented as a typed internal client rather than a public HTTP proxy:

- `domain/unifi_web_api_models.py` defines immutable request/response DTOs;
- `infrastructure/unifi_web_api_client.py` implements the transport;
- `application/ports.py` exposes `UniFiWebConsolePort` to use cases;
- `application/bootstrap.py` orchestrates the configuration workflow.

The DTOs preserve unknown response fields under `raw` for forward compatibility and hide
passwords, MFA tokens, cookies, session tokens, private keys, and full API keys from their
representations. The boundary is deliberately suitable for future extraction as a standalone
`unifi-web-api` package.


## Security classification

This workflow operates with an authenticated UniFi OS administrator web session. It can create a persistent API key and therefore has security impact beyond the read-only Network Integration client.

Never record or commit any of the following:

- `TOKEN` or `JSESSIONID` cookies;
- CSRF tokens;
- administrator passwords or 2FA tokens;
- a complete API key;
- private certificate keys;
- complete browser exports containing any of the above.

Values in examples below are placeholders only.

## Create a local UniFi API key

### Purpose

Creates a new API key for the authenticated local UniFi user. The returned `full_api_key` is normally available only in the creation response and must be captured in memory immediately.

### Request

```http
POST https://<unifi-console-host>/proxy/users/api/v2/user/<user-id>/keys HTTP/1.1
Host: <unifi-console-host>
Accept: */*
Content-Type: text/plain;charset=UTF-8
X-Csrf-Token: <csrf-token>
Cookie: TOKEN=<session-token>; JSESSIONID=<session-id>
Origin: https://<unifi-console-host>
```

Observed path template:

```text
/proxy/users/api/v2/user/{user_id}/keys
```

Observed response status:

```text
HTTP 200 OK
```

#### Required request components

| Component | Required | Description |
|---|---:|---|
| HTTPS console URL | Yes | The local UniFi OS console origin. |
| `user-id` path parameter | Yes | UUID of the authenticated UniFi user. |
| `TOKEN` cookie | Yes | Session credential created by the web-console login. Keep in memory only. |
| CSRF token | Yes | Sent as `X-Csrf-Token`; the login session also contains a CSRF value. |
| JSON request body | Yes | Key name and description. |

Headers such as browser `sec-*`, analytics cookies, `dnt`, `priority`, and `user-agent` were present in the browser capture but are not part of the minimum observed contract and should not be copied without evidence that a specific firmware requires them.

### Request body

The browser sent a JSON object while declaring the body as `text/plain;charset=UTF-8`:

```json
{
  "description": "<description>",
  "name": "<key-name>"
}
```

For `unifi-observer`, the intended values are:

```json
{
  "description": "UniFi Observer local integration key",
  "name": "unifi-observer"
}
```

The request body must not contain the administrator password, 2FA token, cookies, or certificate material.

### Response

Observed successful response shape:

```json
{
  "code": 1,
  "codeS": "SUCCESS",
  "msg": "success",
  "data": {
    "id": "<api-key-id>",
    "name": "<key-name>",
    "description": "<description>",
    "creator_user_id": "<user-id>",
    "created_at": "<timestamp>",
    "updated_at": "<timestamp>",
    "full_api_key": "[REDACTED]",
    "key_permissions": [],
    "permissions": {},
    "scopes": []
  }
}
```

The real response also contained a large permissions and scopes collection. It must be treated as sensitive authorization metadata and should not be copied into logs or documentation.

The adapter must:

1. require HTTP success;
2. parse the response as JSON;
3. require `data.full_api_key` to be a non-empty string;
4. return the key only to the in-memory configuration flow;
5. persist it only after the subsequent connection verification succeeds;
6. never print the complete value;
7. close the web session in a `finally` block.

### Permissions warning

The observed response granted broad administrator permissions to the generated key. The application-level setting:

```env
UNIFI_ENABLE_WRITE=false
```

keeps `unifi-observer` read-only, but it does **not** reduce the privileges encoded in the UniFi API key.

For production use, prefer a dedicated local UniFi account with the minimum permissions supported by the console. If the firmware does not provide a sufficiently restricted key for the required Network Integration endpoints, document that limitation and require explicit user approval before persisting the key.

## Authentication and session prerequisites

The key-creation request is downstream of the web-console login flow:

```text
POST /api/auth/login
        ↓
TOKEN cookie + CSRF token
        ↓
extract authenticated user ID
        ↓
POST /proxy/users/api/v2/user/{user-id}/keys
```

If UniFi responds with the known 2FA challenge, the client must ask for the one-time token interactively and retry the login. The 2FA token must not be persisted.

A failed login must be reported separately from an upload failure. In particular:

- `HTTP 401`: credentials or local-account authorization rejected;
- `HTTP 403`: authenticated account lacks permission;
- `HTTP 499` with `api.err.Ubic2faTokenRequired`: an interactive 2FA token is required;
- connection timeout/DNS/TLS errors: the console could not be reached;
- `4xx/5xx` after authentication: inspect the operation-specific endpoint and upstream code.

## Login: first SSO/MFA step

### Request

```http
POST https://<unifi-console-host>/api/auth/login HTTP/1.1
Host: <unifi-console-host>
Accept: */*
Content-Type: application/json
Origin: https://<unifi-console-host>
Cookie: JSESSIONID=<session-id>
```

The browser sent the following body shape:

```json
{
  "username": "<username>",
  "password": "[REDACTED]",
  "token": "",
  "rememberMe": false
}
```

`token` is empty during the first request. It must not be populated with a guessed value and the administrator password must never be logged or written to configuration.

Browser-only headers (`sec-*`, analytics cookies, device hints, and user-agent) were present in the capture but are not currently treated as required by the adapter.

### MFA challenge response

For the observed SSO account, UniFi returned:

```http
HTTP 499
Content-Type: application/json; charset=utf-8
```

The stable challenge markers were:

```json
{
  "code": "MFA_AUTH_REQUIRED",
  "message": "MFA token required to authenticate to SSO",
  "data": {
    "required": "2fa",
    "mfaCookie": "[REDACTED]",
    "authenticators": [
      {"type": "email", "status": "active"},
      {"type": "webauthn", "status": "active"}
    ],
    "user": {
      "id": "<sso-user-id>",
      "default_mfa": "<authenticator-id>"
    },
    "publicKeyCredentialRequestOptions": {
      "rpId": "ui.com",
      "timeout": 60000,
      "challenge": "[REDACTED]"
    }
  }
}
```

The complete response may contain masked email addresses, authenticator identifiers, WebAuthn credential identifiers, a challenge, and an `UBIC_2FA`-style temporary cookie. These values are sensitive and must not be logged or documented in full.

### Meaning of HTTP 499 in this flow

This response is not a generic network failure and does not mean that certificate upload failed. It means:

1. UniFi reached the SSO authentication stage;
2. the account/password step produced an MFA challenge;
3. the first login request is incomplete;
4. the temporary MFA cookie/challenge context must be carried into the next verification request;
5. no permanent session `TOKEN` or API key should be created yet.

The current adapter recognizes both this SSO marker and the older observed marker:

```text
api.err.Ubic2faTokenRequired
```

For `MFA_AUTH_REQUIRED`, the adapter stores the temporary MFA cookie only in memory. The browser then repeats the same `/api/auth/login` request with the one-time token:

```json
{
  "username": "<username>",
  "password": "[REDACTED]",
  "token": "<six-digit-mfa-code>",
  "rememberMe": false
}
```

The observed successful response was:

```http
HTTP 200 OK
Set-Cookie: TOKEN=[REDACTED]; Path=/; ...
X-Csrf-Token: <csrf-token>
X-Updated-Csrf-Token: <csrf-token>
X-Token-Expire-Time: <epoch-milliseconds>
```

The response body is a user profile object. The adapter needs only the authenticated identity and the session credentials; fields such as permissions, scopes, `deviceToken`, `ssoAuth`, email addresses, and account metadata must not be logged or persisted. The `TOKEN` cookie and CSRF response header are then used by the subsequent certificate and API-key calls.

The current adapter now performs this retry on the same HTTP client, preserving the session cookies received during the first request. It sends the observed empty `token` field on the first request and the supplied one-time code on the second request. It does not add the `mfaCookie` to the second request because it was not present in the captured browser `Cookie` header; the value is still retained only as temporary challenge context and cleared after successful authentication or session close.

### Security and lifecycle

- The `mfaCookie` is a bearer-like temporary credential and must be treated as a secret.
- It must never appear in logs, exceptions, tests with realistic values, commits, or the final summary.
- It must be cleared when the uploader closes or the flow terminates.
- The final UniFi `TOKEN` cookie must remain in memory only during bootstrap.
- The administrator password and the one-time MFA value must never be persisted.
## Compatibility policy

Because these routes are used by the UniFi web application rather than exposed as a documented public contract:

- pin and record the tested UniFi OS/Network versions;
- keep endpoint paths in one infrastructure adapter;
- use explicit response-shape validation;
- classify status codes and upstream error codes without logging response bodies;
- do not use the web session as the permanent MCP credential;
- use the official/local Network Integration API key for normal Observer operation;
- provide a guided manual key-creation fallback;
- do not leave certificate bootstrap in a permanent `verify=False` mode.

## Safe implementation pseudocode

```python
await uploader.authenticate(username, password, two_factor_token)

api_key = await uploader.create_api_key(
    name="unifi-observer",
    description="UniFi Observer local integration key",
)

# Keep api_key in memory. Verify TLS and the selected site before writing config.env.
await uploader.aclose()
```

The pseudocode is intentionally incomplete: the concrete adapter must validate the firmware response, enforce the configuration transaction boundary, and ensure that error messages never contain credential-bearing request or response data.

## Capture record for future calls

When documenting another browser call, record only the following safe metadata:

```text
Operation:
Observed date:
UniFi OS version:
Network application version:
Request method:
Request path:
HTTP status:
Required non-secret headers:
Request body shape with values redacted:
Response shape with secrets and large permission lists redacted:
Session prerequisite:
Known side effects:
Rollback or revocation procedure:
Compatibility notes:
```
