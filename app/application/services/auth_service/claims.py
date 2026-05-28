from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from app.application.domain import (
    PrincipalIdentity,
    PrincipalType,
    Role,
    principal_id_to_subject,
    subject_to_principal_id,
)

from .errors import raise_invalid_credentials


@dataclass(frozen=True, slots=True)
class IdentityClaims:
    principal_id: int
    username: str
    role: Role
    principal_type: PrincipalType
    token_id: str


def build_token_claims(
    principal: PrincipalIdentity,
    token_id: str,
    issued_at: datetime,
    expires_at: datetime,
) -> dict[str, object]:
    return {
        "sub": principal_id_to_subject(principal.id),
        "username": principal.username,
        "role": principal.role.value,
        "principal_type": principal.principal_type.value,
        "jti": token_id,
        "iat": issued_at,
        "exp": expires_at,
    }


def parse_identity_claims(claims: Mapping[str, object]) -> IdentityClaims:
    return IdentityClaims(
        token_id=required_string_claim(claims, "jti"),
        principal_id=subject_to_principal_id(required_string_claim(claims, "sub")),
        username=required_string_claim(claims, "username"),
        role=role_from_claim(required_string_claim(claims, "role")),
        principal_type=principal_type_from_claim(
            required_string_claim(claims, "principal_type")
        ),
    )


def required_string_claim(claims: Mapping[str, object], name: str) -> str:
    claim: object | None = claims.get(name)

    if not isinstance(claim, str) or claim.strip() == "":
        raise_invalid_credentials()

    return claim


def role_from_claim(claim: str) -> Role:
    try:
        return Role(claim)
    except ValueError:
        raise_invalid_credentials()


def principal_type_from_claim(claim: str) -> PrincipalType:
    try:
        return PrincipalType(claim)
    except ValueError:
        raise_invalid_credentials()
