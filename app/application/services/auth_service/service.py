from collections.abc import Callable, Mapping
from datetime import datetime, timedelta

from app.application.domain import (
    AuthenticatedUser,
    LoginResult,
    PrincipalIdentity,
    PrincipalType,
    TokenSession,
)
from app.application.ports import CredentialsGateway, TokenCodec, TokenSessionGateway

from .claims import IdentityClaims, build_token_claims, parse_identity_claims
from .errors import raise_invalid_credentials
from .tokens import TOKEN_EXPIRATION_DAYS, new_token_id, utc_now
from .users import build_authenticated_user


class AuthService:
    def __init__(
        self,
        credentials_gateway: CredentialsGateway,
        token_session_gateway: TokenSessionGateway,
        token_codec: TokenCodec,
        clock: Callable[[], datetime] = utc_now,
        token_id_factory: Callable[[], str] = new_token_id,
    ) -> None:
        self._credentials_gateway = credentials_gateway
        self._token_session_gateway = token_session_gateway
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
            principal = await self._credentials_gateway.authenticate_internal_user(
                username=username,
                password=password,
            )
            return await self.issue_token(principal)

        if principal_type is PrincipalType.CUSTOMER:
            principal = await self._credentials_gateway.authenticate_customer(
                username=username,
                password=password,
            )
            return await self.issue_token(principal)

        raise_invalid_credentials()

    async def issue_token(self, principal: PrincipalIdentity) -> LoginResult:
        token_id: str = self._token_id_factory()
        issued_at: datetime = self._clock()
        expires_at: datetime = issued_at + timedelta(days=TOKEN_EXPIRATION_DAYS)

        claims: dict[str, object] = build_token_claims(
            principal=principal,
            token_id=token_id,
            issued_at=issued_at,
            expires_at=expires_at,
        )
        access_token: str = self._token_codec.encode(claims)
        session = TokenSession(
            token_id=token_id,
            principal_id=principal.id,
            principal_type=principal.principal_type,
            issued_at=issued_at,
            expires_at=expires_at,
        )
        await self._token_session_gateway.register_token_session(session)

        user: AuthenticatedUser = build_authenticated_user(
            principal_id=principal.id,
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
        identity_claims: IdentityClaims = parse_identity_claims(claims)

        if not await self._token_session_gateway.is_token_known(
            identity_claims.token_id
        ):
            raise_invalid_credentials()

        session: (
            TokenSession | None
        ) = await self._token_session_gateway.get_token_session(
            identity_claims.token_id
        )
        if session is None:
            raise_invalid_credentials()

        if (
            session.token_id != identity_claims.token_id
            or session.principal_id != identity_claims.principal_id
            or session.principal_type is not identity_claims.principal_type
        ):
            raise_invalid_credentials()

        if await self._token_session_gateway.is_token_revoked(identity_claims.token_id):
            raise_invalid_credentials()

        if session.expires_at <= self._clock():
            raise_invalid_credentials()

        return build_authenticated_user(
            principal_id=identity_claims.principal_id,
            username=identity_claims.username,
            role=identity_claims.role,
            principal_type=identity_claims.principal_type,
            token_id=identity_claims.token_id,
        )

    async def revoke_token(self, token_id: str) -> None:
        if token_id.strip() == "":
            raise_invalid_credentials()

        if not await self._token_session_gateway.is_token_known(token_id):
            raise_invalid_credentials()

        await self._token_session_gateway.revoke_token(token_id)
