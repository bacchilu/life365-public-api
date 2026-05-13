from collections.abc import Mapping
from typing import cast

import jwt

from app.application.exceptions import AuthenticationException
from app.application.ports import TokenCodec

JWT_ALGORITHM = "HS256"
_INVALID_CREDENTIALS_MESSAGE = "Invalid credentials"


class PyJWTTokenCodec(TokenCodec):
    def __init__(self, secret_key: str) -> None:
        self._secret_key = secret_key

    def encode(self, claims: Mapping[str, object]) -> str:
        return jwt.encode(dict(claims), self._secret_key, algorithm=JWT_ALGORITHM)

    def decode(self, token: str) -> Mapping[str, object]:
        try:
            decoded: object = jwt.decode(
                token, self._secret_key, algorithms=[JWT_ALGORITHM]
            )
        except jwt.PyJWTError as exc:
            raise AuthenticationException(_INVALID_CREDENTIALS_MESSAGE) from exc

        if not isinstance(decoded, dict):
            raise AuthenticationException(_INVALID_CREDENTIALS_MESSAGE)

        return cast(dict[str, object], decoded)
