from typing import NoReturn

import psycopg
from psycopg import sql
from psycopg.rows import TupleRow

from app.application.domain import PrincipalIdentity, PrincipalType, Role
from app.application.exceptions import AuthenticationException

from .passwords import verify_legacy_password

_INVALID_CREDENTIALS_MESSAGE = "Invalid credentials"

INTERNAL_USER_COLUMNS: tuple[str, ...] = (
    "id",
    "username",
    "password",
    "role",
    "enabled",
)

QUERY = sql.SQL("SELECT {columns} FROM {table} WHERE {username_column} = %s").format(
    columns=sql.SQL(", ").join(
        sql.Identifier(column) for column in INTERNAL_USER_COLUMNS
    ),
    table=sql.Identifier("public", "users"),
    username_column=sql.Identifier("username"),
)


def _raise_invalid_credentials() -> NoReturn:
    raise AuthenticationException(_INVALID_CREDENTIALS_MESSAGE)


async def get_internal_user_row(
    cur: psycopg.AsyncCursor[TupleRow],
    username: str,
) -> TupleRow | None:
    await cur.execute(QUERY, (username,))
    rows: list[TupleRow] = await cur.fetchall()

    if len(rows) != 1:
        return None

    return rows[0]


def internal_user_identity_from_row(
    row: TupleRow,
    submitted_password: str,
) -> PrincipalIdentity:
    if len(row) != len(INTERNAL_USER_COLUMNS):
        _raise_invalid_credentials()

    principal_id = row[0]
    username = row[1]
    stored_credential = row[2]
    source_role = row[3]
    enabled = row[4]

    if type(principal_id) is not int or principal_id <= 0:
        _raise_invalid_credentials()

    if not isinstance(username, str) or username == "":
        _raise_invalid_credentials()

    if not isinstance(stored_credential, str):
        _raise_invalid_credentials()

    if not isinstance(source_role, str):
        _raise_invalid_credentials()

    if enabled is not True:
        _raise_invalid_credentials()

    if not verify_legacy_password(submitted_password, stored_credential):
        _raise_invalid_credentials()

    return PrincipalIdentity(
        id=principal_id,
        username=username,
        role=Role.from_internal_role(source_role),
        principal_type=PrincipalType.from_internal_user(),
    )
