from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.application.domain import (
    AuthenticatedUser,
    LoginResult,
    PrincipalIdentity,
    TokenSession,
    principal_id_to_subject,
)
from app.application.ports import AuthenticationGateway, TokenCodec

TOKEN_EXPIRATION_DAYS = 30


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _new_token_id() -> str:
    return str(uuid4())


class AuthService:
    def __init__(
        self,
        authentication_gateway: AuthenticationGateway,
        token_codec: TokenCodec,
        clock: Callable[[], datetime] = _utc_now,
        token_id_factory: Callable[[], str] = _new_token_id,
    ) -> None:
        self._authentication_gateway = authentication_gateway
        self._token_codec = token_codec
        self._clock = clock
        self._token_id_factory = token_id_factory

    async def issue_token(self, principal: PrincipalIdentity) -> LoginResult:
        token_id: str = self._token_id_factory()
        issued_at: datetime = self._clock()
        expires_at: datetime = issued_at + timedelta(days=TOKEN_EXPIRATION_DAYS)

        claims: dict[str, object] = {
            "sub": principal_id_to_subject(principal.id),
            "username": principal.username,
            "role": principal.role.value,
            "principal_type": principal.principal_type.value,
            "jti": token_id,
            "iat": issued_at,
            "exp": expires_at,
        }
        access_token: str = self._token_codec.encode(claims)
        session = TokenSession(
            token_id=token_id,
            principal_id=principal.id,
            principal_type=principal.principal_type,
            issued_at=issued_at,
            expires_at=expires_at,
        )
        await self._authentication_gateway.register_token_session(session)

        user = AuthenticatedUser(
            id=principal.id,
            username=principal.username,
            role=principal.role,
            principal_type=principal.principal_type,
            token_id=token_id,
        )

        return LoginResult(
            user=user,
            session=session,
            access_token=access_token,
        )
