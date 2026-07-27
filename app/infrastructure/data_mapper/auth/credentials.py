from psycopg.rows import TupleRow

from app.application.domain import PrincipalIdentity
from app.application.exceptions import AuthenticationException
from app.application.ports import CredentialsGateway
from app.infrastructure.data_mapper.connection import get_cursor_context

from .customer import customer_identity_from_row, get_customer_row
from .internal_user import get_internal_user_row, internal_user_identity_from_row

_INVALID_CREDENTIALS_MESSAGE = "Invalid credentials"


class CredentialsDataMapper(CredentialsGateway):
    def __init__(self, connection_string: str) -> None:
        self._connection_string = connection_string

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
