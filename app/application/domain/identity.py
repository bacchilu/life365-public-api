from dataclasses import dataclass
from enum import StrEnum

from app.application.exceptions import AuthenticationException

_INVALID_CREDENTIALS_MESSAGE = "Invalid credentials"


class Role(StrEnum):
    ADMIN = "admin"
    BUYER = "buyer"
    CUSTOMER = "customer"

    @classmethod
    def from_internal_role(cls, source_role: str) -> "Role":
        normalized_role: str = source_role.strip().upper()

        if normalized_role == "ADMIN":
            return cls.ADMIN

        if normalized_role == "BUYER":
            return cls.BUYER

        raise AuthenticationException(_INVALID_CREDENTIALS_MESSAGE)

    @classmethod
    def from_customer(cls) -> "Role":
        return cls.CUSTOMER


class PrincipalType(StrEnum):
    USER = "user"
    CUSTOMER = "customer"

    @classmethod
    def from_internal_user(cls) -> "PrincipalType":
        return cls.USER

    @classmethod
    def from_customer(cls) -> "PrincipalType":
        return cls.CUSTOMER


@dataclass(frozen=True, slots=True)
class PrincipalIdentity:
    id: int
    username: str
    role: Role
    principal_type: PrincipalType
