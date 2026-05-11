from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class Role(StrEnum):
    ADMIN = "admin"
    BUYER = "buyer"
    CUSTOMER = "customer"


class PrincipalType(StrEnum):
    USER = "user"
    CUSTOMER = "customer"


@dataclass(frozen=True, slots=True)
class AuthenticatedUser:
    id: int
    username: str
    role: Role
    principal_type: PrincipalType
    token_id: str


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
