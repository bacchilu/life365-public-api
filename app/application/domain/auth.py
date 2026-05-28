from dataclasses import dataclass, field
from datetime import datetime

from app.application.domain.authorization import Permission, ProductAccessPolicy
from app.application.domain.identity import PrincipalType, Role
from app.application.exceptions import AuthenticationException

_INVALID_CREDENTIALS_MESSAGE = "Invalid credentials"


@dataclass(frozen=True, slots=True)
class AuthenticatedUser:
    id: int
    username: str
    role: Role
    principal_type: PrincipalType
    token_id: str
    permissions: frozenset[Permission]
    product_access: ProductAccessPolicy


@dataclass(frozen=True, slots=True)
class TokenSession:
    token_id: str
    principal_id: int
    principal_type: PrincipalType
    issued_at: datetime
    expires_at: datetime
    revoked: bool = False


@dataclass(frozen=True, slots=True)
class LoginResult:
    user: AuthenticatedUser
    session: TokenSession
    access_token: str = field(repr=False)


def principal_id_to_subject(principal_id: int) -> str:
    if type(principal_id) is not int or principal_id <= 0:
        raise AuthenticationException(_INVALID_CREDENTIALS_MESSAGE)

    return str(principal_id)


def subject_to_principal_id(subject: str) -> int:
    normalized_subject: str = subject.strip()

    if not normalized_subject.isdecimal():
        raise AuthenticationException(_INVALID_CREDENTIALS_MESSAGE)

    principal_id: int = int(normalized_subject)

    if principal_id <= 0:
        raise AuthenticationException(_INVALID_CREDENTIALS_MESSAGE)

    return principal_id
