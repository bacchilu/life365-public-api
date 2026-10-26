from collections.abc import Mapping
from typing import cast

import jwt

from app.application.exceptions import AuthenticationException
from app.application.ports import TokenCodec

JWT_ALGORITHM = "HS256"
_INVALID_CREDENTIALS_MESSAGE = "Invalid credentials"


class PyJWTTokenCodec(TokenCodec):
    def __init__(
        self, secret_key: str, *, issuer: str | None = None, audience: str | None = None
    ) -> None:
        self._secret_key = secret_key
        self._issuer = issuer
        self._audience = audience

    def encode(self, claims: Mapping[str, object]) -> str:
        payload = dict(claims)
        if self._issuer is not None:
            payload["iss"] = self._issuer
        if self._audience is not None:
            payload["aud"] = self._audience
        return jwt.encode(payload, self._secret_key, algorithm=JWT_ALGORITHM)

    def decode(self, token: str) -> Mapping[str, object]:
        try:
            decoded: object = jwt.decode(
                token,
                self._secret_key,
                algorithms=[JWT_ALGORITHM],
                issuer=self._issuer,
                audience=self._audience,
                options={
                    "require": [
                        name
                        for name, value in (
                            ("iss", self._issuer),
                            ("aud", self._audience),
                        )
                        if value is not None
                    ]
                },
            )
        except jwt.PyJWTError as exc:
            raise AuthenticationException(_INVALID_CREDENTIALS_MESSAGE) from exc

        if not isinstance(decoded, dict):
            raise AuthenticationException(_INVALID_CREDENTIALS_MESSAGE)

        return cast(dict[str, object], decoded)
