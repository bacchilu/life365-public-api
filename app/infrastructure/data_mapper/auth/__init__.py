__all__ = [
    "AuthenticationDataMapper",
    "customer_identity_from_row",
    "get_customer_row",
    "get_internal_user_row",
    "internal_user_identity_from_row",
    "verify_legacy_password",
]

from psycopg.rows import TupleRow

from app.application.domain import PrincipalIdentity, TokenSession
from app.application.exceptions import AuthenticationException
from app.application.ports import AuthenticationGateway
from app.infrastructure.data_mapper.connection import get_cursor_context

from .customer import customer_identity_from_row, get_customer_row
from .internal_user import get_internal_user_row, internal_user_identity_from_row
from .passwords import verify_legacy_password

_INVALID_CREDENTIALS_MESSAGE = "Invalid credentials"


class AuthenticationDataMapper(AuthenticationGateway):
    def __init__(self, connection_string: str) -> None:
        self._connection_string = connection_string
        self._sessions: dict[str, TokenSession] = {}
        self._revoked_token_ids: set[str] = set()

    async def authenticate_internal_user(
        self, username: str, password: str
    ) -> PrincipalIdentity:
        async with get_cursor_context(self._connection_string) as cur:
            row: TupleRow | None = await get_internal_user_row(cur, username)

        if row is None:
            raise AuthenticationException(_INVALID_CREDENTIALS_MESSAGE)

        return internal_user_identity_from_row(row, password)

    async def authenticate_customer(
        self, username: str, password: str
    ) -> PrincipalIdentity:
        async with get_cursor_context(self._connection_string) as cur:
            row: TupleRow | None = await get_customer_row(cur, username)

        if row is None:
            raise AuthenticationException(_INVALID_CREDENTIALS_MESSAGE)

        return customer_identity_from_row(row, password)

    async def register_token_session(self, session: TokenSession) -> None:
        self._sessions[session.token_id] = session

    async def get_token_session(self, token_id: str) -> TokenSession | None:
        return self._sessions.get(token_id)

    async def is_token_known(self, token_id: str) -> bool:
        return token_id in self._sessions

    async def is_token_revoked(self, token_id: str) -> bool:
        session: TokenSession | None = self._sessions.get(token_id)
        return token_id in self._revoked_token_ids or (
            session is not None and session.revoked
        )

    async def revoke_token(self, token_id: str) -> None:
        self._revoked_token_ids.add(token_id)
