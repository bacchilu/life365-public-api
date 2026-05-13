from collections.abc import Mapping
from datetime import datetime, timezone
from typing import NoReturn
from uuid import uuid4

from app.application.domain import PrincipalType, Role
from app.application.exceptions import AuthenticationException

INVALID_CREDENTIALS_MESSAGE = "Invalid credentials"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_token_id() -> str:
    return str(uuid4())


def raise_invalid_credentials() -> NoReturn:
    raise AuthenticationException(INVALID_CREDENTIALS_MESSAGE)


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
