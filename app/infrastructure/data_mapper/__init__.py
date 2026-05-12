__all__ = [
    "AuthenticationDataMapper",
    "CheckDataMapper",
    "DATABASE_URL",
    "ProductsDataMapper",
]

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import psycopg
from dotenv import load_dotenv
from psycopg.rows import TupleRow

from app.application.domain import PrincipalIdentity, Product, TokenSession
from app.application.exceptions import AuthenticationException
from app.application.ports import AuthenticationGateway, CheckGateway, ProductsGateway
from app.infrastructure.data_mapper.auth import (
    customer_identity_from_row,
    get_customer_row,
    get_internal_user_row,
    internal_user_identity_from_row,
)
from app.infrastructure.data_mapper.products import get_product as execute_get_product
from app.infrastructure.data_mapper.products import get_products as execute_get_products

load_dotenv()
DATABASE_URL: str = os.environ["DATABASE_URL"]
_INVALID_CREDENTIALS_MESSAGE = "Invalid credentials"


@asynccontextmanager
async def get_cursor_context(
    connection_string: str,
) -> AsyncIterator[psycopg.AsyncCursor[TupleRow]]:
    async with await psycopg.AsyncConnection.connect(connection_string) as conn:
        async with conn.cursor() as cur:
            yield cur


class CheckDataMapper(CheckGateway):
    def __init__(self, connection_string: str) -> None:
        self._connection_string = connection_string

    async def check_db(self) -> bool:
        async with get_cursor_context(self._connection_string) as cur:
            await cur.execute("SELECT 1")
            row: TupleRow | None = await cur.fetchone()
            return row is not None and row[0] == 1


class AuthenticationDataMapper(AuthenticationGateway):
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

    async def register_token_session(self, session: TokenSession) -> None:
        raise NotImplementedError("Token session storage is not implemented yet")

    async def get_token_session(self, token_id: str) -> TokenSession | None:
        raise NotImplementedError("Token session storage is not implemented yet")

    async def is_token_known(self, token_id: str) -> bool:
        raise NotImplementedError("Token session storage is not implemented yet")

    async def is_token_revoked(self, token_id: str) -> bool:
        raise NotImplementedError("Token revocation is not implemented yet")

    async def revoke_token(self, token_id: str) -> None:
        raise NotImplementedError("Token revocation is not implemented yet")


class ProductsDataMapper(ProductsGateway):
    def __init__(self, connection_string: str) -> None:
        self._connection_string = connection_string

    async def get_products(self, limit: int = 100, offset: int = 0) -> list[Product]:
        if limit < 1:
            raise ValueError("limit must be greater than 0")
        if offset < 0:
            raise ValueError("offset must be greater than or equal to 0")

        async with get_cursor_context(self._connection_string) as cur:
            return await execute_get_products(cur, limit=limit, offset=offset)

    async def get_product(self, product_id: int) -> Product:
        async with get_cursor_context(self._connection_string) as cur:
            res: Product | None = await execute_get_product(cur, product_id)
            if res is None:
                raise Exception(f"We don't have a product with {product_id} product id")
            return res
