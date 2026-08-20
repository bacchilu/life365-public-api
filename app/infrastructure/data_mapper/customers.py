from typing import Any

import psycopg
from psycopg import sql
from psycopg.rows import TupleRow

from app.application.domain import Customer
from app.application.ports import CustomersGateway
from app.infrastructure.data_mapper.connection import get_cursor_context

CUSTOMER_COLUMNS: tuple[str, ...] = (
    "id",
    "login",
    "email",
    "business_name",
    "business_contact_name",
    "preferred_language",
    "extra_data",
    "parameters",
    "last_login_date",
)

QUERY = sql.SQL(
    "SELECT {columns} FROM {table} ORDER BY {id_column} LIMIT %s OFFSET %s"
).format(
    columns=sql.SQL(", ").join(sql.Identifier(column) for column in CUSTOMER_COLUMNS),
    table=sql.Identifier("public", "customers"),
    id_column=sql.Identifier("id"),
)


def _dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _customer_from_row(row: TupleRow) -> Customer:
    return Customer(
        id=row[0],
        login=row[1],
        email=row[2],
        business_name=row[3],
        business_contact_name=row[4],
        preferred_language=row[5],
        extra_data=_dict(row[6]),
        parameters=_dict(row[7]),
        last_login_date=row[8],
    )


async def _get_customers(
    cur: psycopg.AsyncCursor[TupleRow], limit: int, offset: int
) -> list[Customer]:
    await cur.execute(QUERY, (limit, offset))
    rows: list[TupleRow] = await cur.fetchall()
    return [_customer_from_row(row) for row in rows]


class InMemoryCustomersDataMapper(CustomersGateway):
    def __init__(self) -> None:
        self._customers: tuple[Customer, ...] = (
            Customer(
                id=1,
                login="customer-login",
                email="customer@example.com",
                business_name="Example Business",
                business_contact_name="Example Contact",
                preferred_language="it",
            ),
            Customer(
                id=2,
                login="second-customer",
                email="second.customer@example.com",
                business_name="Second Business",
                business_contact_name="Second Contact",
                preferred_language="en",
            ),
        )

    async def get_customers(self, limit: int = 100, offset: int = 0) -> list[Customer]:
        if limit < 1:
            raise ValueError("limit must be greater than 0")
        if offset < 0:
            raise ValueError("offset must be greater than or equal to 0")

        return list(self._customers[offset : offset + limit])


class PostgreSQLCustomersDataMapper(CustomersGateway):
    def __init__(self, connection_string: str) -> None:
        self._connection_string = connection_string

    async def get_customers(self, limit: int = 100, offset: int = 0) -> list[Customer]:
        if limit < 1:
            raise ValueError("limit must be greater than 0")
        if offset < 0:
            raise ValueError("offset must be greater than or equal to 0")

        async with get_cursor_context(self._connection_string) as cur:
            return await _get_customers(cur, limit=limit, offset=offset)
