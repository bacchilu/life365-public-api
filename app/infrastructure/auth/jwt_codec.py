from collections.abc import Mapping

import jwt

from app.application.ports import TokenCodec

JWT_ALGORITHM = "HS256"


class PyJWTTokenCodec(TokenCodec):
    def __init__(self, secret_key: str) -> None:
        self._secret_key = secret_key

    def encode(self, claims: Mapping[str, object]) -> str:
        return jwt.encode(dict(claims), self._secret_key, algorithm=JWT_ALGORITHM)
