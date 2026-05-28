from typing import NoReturn

from app.application.exceptions import AuthenticationException

INVALID_CREDENTIALS_MESSAGE = "Invalid credentials"


def raise_invalid_credentials() -> NoReturn:
    raise AuthenticationException(INVALID_CREDENTIALS_MESSAGE)
