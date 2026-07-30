import os
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Protocol

from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.application.domain import AuthenticatedUser
from app.application.exceptions import AuthenticationException
from app.application.ports import TokenSessionGateway
from app.application.services.auth_service import AuthService

_INVALID_CREDENTIALS_DETAIL = "Invalid credentials"
_WWW_AUTHENTICATE_BEARER = {"WWW-Authenticate": "Bearer"}


class TokenSessionBackend(StrEnum):
    MEMORY = "memory"
    SQLITE = "sqlite"


TOKEN_SESSION_BACKEND: TokenSessionBackend = TokenSessionBackend.SQLITE
SQLITE_TOKEN_SESSION_DATABASE_PATH = Path(
    os.environ.get(
        "TOKEN_SESSION_DATABASE_PATH",
        "data/token-sessions.sqlite3",
    )
)

bearer_token = HTTPBearer(auto_error=False)
_auth_service: AuthService | None = None


class AuthTokenValidator(Protocol):
    async def validate_token(self, token: str | None) -> AuthenticatedUser: ...


def auth_exception() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=_INVALID_CREDENTIALS_DETAIL,
        headers=_WWW_AUTHENTICATE_BEARER,
    )


def _jwt_secret_key() -> str:
    load_dotenv()
    secret_key: str | None = os.environ.get("JWT_SECRET_KEY")

    if secret_key is None or secret_key.strip() == "":
        raise RuntimeError("JWT_SECRET_KEY is not configured")

    return secret_key


async def _create_token_session_gateway() -> TokenSessionGateway:
    from app.infrastructure.data_mapper.auth import (
        InMemoryTokenSessionDataMapper,
        SQLiteTokenSessionDataMapper,
    )

    if TOKEN_SESSION_BACKEND is TokenSessionBackend.MEMORY:
        return InMemoryTokenSessionDataMapper()

    if TOKEN_SESSION_BACKEND is TokenSessionBackend.SQLITE:
        data_mapper: TokenSessionGateway = SQLiteTokenSessionDataMapper(
            SQLITE_TOKEN_SESSION_DATABASE_PATH
        )
        await data_mapper.initialize()
        return data_mapper

    raise RuntimeError(f"Unsupported token session backend: {TOKEN_SESSION_BACKEND}")


async def get_auth_service() -> AuthService:
    global _auth_service

    if _auth_service is None:
        from app.infrastructure.auth import PyJWTTokenCodec
        from app.infrastructure.data_mapper import (
            DATABASE_URL,
            CredentialsDataMapper,
        )

        _auth_service = AuthService(
            credentials_gateway=CredentialsDataMapper(DATABASE_URL),
            token_session_gateway=await _create_token_session_gateway(),
            token_codec=PyJWTTokenCodec(_jwt_secret_key()),
        )

    return _auth_service


async def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_token),
    ],
    auth_service: Annotated[AuthTokenValidator, Depends(get_auth_service)],
) -> AuthenticatedUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise auth_exception()

    try:
        return await auth_service.validate_token(credentials.credentials)
    except AuthenticationException as exc:
        raise auth_exception() from exc
