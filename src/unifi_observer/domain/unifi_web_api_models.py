"""Typed DTOs for the observed UniFi OS web-console API contract.

These models are transport-facing contracts. They deliberately preserve unknown
upstream fields in ``raw`` so a firmware response can evolve without silently
losing information. Secret-bearing fields are excluded from ``repr``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

JsonObject = Mapping[str, Any]


@dataclass(frozen=True)
class LoginRequest:
    username: str
    password: str = field(repr=False)
    token: str = field(default="", repr=False)
    remember_me: bool = False

    def to_payload(self) -> dict[str, Any]:
        return {
            "username": self.username,
            "password": self.password,
            "token": self.token,
            "rememberMe": self.remember_me,
        }


@dataclass(frozen=True)
class TwoFactorRequest(LoginRequest):
    token: str = field(default="", repr=False)


@dataclass(frozen=True)
class SessionCredentials:
    token: str | None = field(default=None, repr=False)
    csrf_token: str | None = field(default=None, repr=False)
    updated_csrf_token: str | None = field(default=None, repr=False)
    token_expire_time: str | None = None


@dataclass(frozen=True)
class MfaAuthenticator:
    id: str | None
    type: str | None
    status: str | None
    email: str | None
    created_at: str | None
    last_success_at: str | None
    blocked_reason: str | None
    raw: JsonObject = field(default_factory=dict, repr=False)


@dataclass(frozen=True)
class MfaChallengeResponse:
    status_code: int
    code: str | None
    message: str | None
    required: str | None
    mfa_cookie: str | None = field(default=None, repr=False)
    authenticators: tuple[MfaAuthenticator, ...] = ()
    raw: JsonObject = field(default_factory=dict, repr=False)


@dataclass(frozen=True)
class UniFiUserProfile:
    user_id: str | None
    unique_id: str | None
    username: str | None
    email: str | None
    first_name: str | None
    last_name: str | None
    role: str | None
    account_type: str | None
    local_account_exist: bool | None
    only_ui_account: bool | None
    cloud_access: bool | None
    scopes: tuple[str, ...] = ()
    permissions: JsonObject = field(default_factory=dict, repr=False)
    raw: JsonObject = field(default_factory=dict, repr=False)


@dataclass(frozen=True)
class LoginSuccessResponse:
    status_code: int
    user: UniFiUserProfile
    session: SessionCredentials
    raw: JsonObject = field(default_factory=dict, repr=False)


LoginResponse = MfaChallengeResponse | LoginSuccessResponse


@dataclass(frozen=True)
class UploadCertificateRequest:
    name: str
    certificate_pem: str = field(repr=False)
    private_key_pem: str = field(repr=False)

    def to_payload(self) -> dict[str, str]:
        return {"name": self.name, "cert": self.certificate_pem, "key": self.private_key_pem}


@dataclass(frozen=True)
class UploadCertificateResponse:
    status_code: int
    certificate_id: str
    raw: JsonObject = field(default_factory=dict, repr=False)


@dataclass(frozen=True)
class ActivateCertificateRequest:
    certificate_id: str
    active: bool = True

    def to_payload(self) -> dict[str, bool]:
        return {"active": self.active}


@dataclass(frozen=True)
class ActivateCertificateResponse:
    status_code: int
    active: bool
    raw: JsonObject = field(default_factory=dict, repr=False)


@dataclass(frozen=True)
class CreateApiKeyRequest:
    user_id: str
    name: str
    description: str

    def to_payload(self) -> dict[str, str]:
        return {"name": self.name, "description": self.description}


@dataclass(frozen=True)
class ApiKeyMetadata:
    key_id: str | None
    name: str | None
    description: str | None
    created_at: str | None
    updated_at: str | None
    scopes: tuple[str, ...] = ()
    full_api_key: str | None = field(default=None, repr=False)
    raw: JsonObject = field(default_factory=dict, repr=False)


@dataclass(frozen=True)
class CreateApiKeyResponse:
    status_code: int
    key: ApiKeyMetadata
    raw: JsonObject = field(default_factory=dict, repr=False)


def _value(payload: JsonObject, key: str) -> Any:
    return payload.get(key)


def _string(payload: JsonObject, key: str) -> str | None:
    value = payload.get(key)
    return value if isinstance(value, str) else None


def _bool(payload: JsonObject, key: str) -> bool | None:
    value = payload.get(key)
    return value if isinstance(value, bool) else None


def _strings(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, str))


def _object(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _profile_payload(payload: JsonObject) -> dict[str, Any]:
    return _object(payload.get("data")) or dict(payload)


def parse_user_profile(payload: JsonObject) -> UniFiUserProfile:
    body = _profile_payload(payload)
    return UniFiUserProfile(
        user_id=_string(body, "id") or _string(body, "userId"),
        unique_id=_string(body, "unique_id") or _string(body, "uniqueId"),
        username=_string(body, "username"),
        email=_string(body, "email"),
        first_name=_string(body, "first_name") or _string(body, "firstName"),
        last_name=_string(body, "last_name") or _string(body, "lastName"),
        role=_string(body, "role"),
        account_type=_string(body, "account_type") or _string(body, "accountType"),
        local_account_exist=_bool(body, "local_account_exist"),
        only_ui_account=_bool(body, "only_ui_account"),
        cloud_access=_bool(body, "cloud_access"),
        scopes=_strings(body.get("scopes")),
        permissions=_object(body.get("permissions")),
        raw=body,
    )


def parse_mfa_challenge(status_code: int, payload: JsonObject) -> MfaChallengeResponse:
    data = _object(payload.get("data"))
    authenticators = tuple(
        MfaAuthenticator(
            id=_string(item, "id"),
            type=_string(item, "type"),
            status=_string(item, "status"),
            email=_string(item, "email"),
            created_at=_string(item, "created") or _string(item, "createdAt"),
            last_success_at=_string(item, "last_success") or _string(item, "lastSuccess"),
            blocked_reason=_string(item, "blocked_reason") or _string(item, "blockedReason"),
            raw=item,
        )
        for raw_item in data.get("authenticators", [])
        for item in [_object(raw_item)]
        if item
    )
    return MfaChallengeResponse(
        status_code=status_code,
        code=_string(payload, "code"),
        message=_string(payload, "message"),
        required=_string(data, "required"),
        mfa_cookie=_string(data, "mfaCookie"),
        authenticators=authenticators,
        raw=payload,
    )


def parse_api_key_response(status_code: int, payload: JsonObject) -> CreateApiKeyResponse:
    data = _object(payload.get("data")) or dict(payload)
    return CreateApiKeyResponse(
        status_code=status_code,
        key=ApiKeyMetadata(
            key_id=_string(data, "id") or _string(data, "key_id"),
            name=_string(data, "name"),
            description=_string(data, "description"),
            created_at=_string(data, "created_at") or _string(data, "createdAt"),
            updated_at=_string(data, "updated_at") or _string(data, "updatedAt"),
            scopes=_strings(data.get("scopes")),
            full_api_key=_string(data, "full_api_key"),
            raw=data,
        ),
        raw=payload,
    )


def parse_payload(response: Any) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError:
        return {}
    return payload if isinstance(payload, dict) else {}
