from collections.abc import Callable, Mapping
from datetime import datetime, timedelta

from app.application.domain import (
    AuthenticatedUser,
    LoginResult,
    PrincipalIdentity,
    PrincipalType,
    Role,
    TokenSession,
    principal_id_to_subject,
    subject_to_principal_id,
)
from app.application.ports import AuthenticationGateway, TokenCodec

from ._utils import (
    new_token_id,
    principal_type_from_claim,
    raise_invalid_credentials,
    required_string_claim,
    role_from_claim,
    utc_now,
)

TOKEN_EXPIRATION_DAYS = 30


class AuthService:
    def __init__(
        self,
        authentication_gateway: AuthenticationGateway,
        token_codec: TokenCodec,
        clock: Callable[[], datetime] = utc_now,
        token_id_factory: Callable[[], str] = new_token_id,
    ) -> None:
        self._authentication_gateway = authentication_gateway
        self._token_codec = token_codec
        self._clock = clock
        self._token_id_factory = token_id_factory

    async def login(
        self,
        username: str,
        password: str,
        principal_type: PrincipalType,
    ) -> LoginResult:
        if principal_type is PrincipalType.USER:
            principal = await self._authentication_gateway.authenticate_internal_user(
                username=username,
                password=password,
            )
            return await self.issue_token(principal)

        if principal_type is PrincipalType.CUSTOMER:
            principal = await self._authentication_gateway.authenticate_customer(
                username=username,
                password=password,
            )
            return await self.issue_token(principal)

        raise_invalid_credentials()

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

    async def validate_token(self, token: str | None) -> AuthenticatedUser:
        if token is None or token.strip() == "":
            raise_invalid_credentials()

        claims: Mapping[str, object] = self._token_codec.decode(token.strip())
        token_id: str = required_string_claim(claims, "jti")
        principal_id: int = subject_to_principal_id(
            required_string_claim(claims, "sub")
        )
        username: str = required_string_claim(claims, "username")
        role: Role = role_from_claim(required_string_claim(claims, "role"))
        principal_type: PrincipalType = principal_type_from_claim(
            required_string_claim(claims, "principal_type")
        )

        if not await self._authentication_gateway.is_token_known(token_id):
            raise_invalid_credentials()

        session: (
            TokenSession | None
        ) = await self._authentication_gateway.get_token_session(token_id)
        if session is None:
            raise_invalid_credentials()

        if (
            session.token_id != token_id
            or session.principal_id != principal_id
            or session.principal_type is not principal_type
        ):
            raise_invalid_credentials()

        if await self._authentication_gateway.is_token_revoked(token_id):
            raise_invalid_credentials()

        if session.expires_at <= self._clock():
            raise_invalid_credentials()

        return AuthenticatedUser(
            id=principal_id,
            username=username,
            role=role,
            principal_type=principal_type,
            token_id=token_id,
        )

    async def revoke_token(self, token_id: str) -> None:
        if token_id.strip() == "":
            raise_invalid_credentials()

        if not await self._authentication_gateway.is_token_known(token_id):
            raise_invalid_credentials()

        await self._authentication_gateway.revoke_token(token_id)
