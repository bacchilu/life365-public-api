from typing import cast

import psycopg
import pytest
from psycopg.rows import TupleRow

from app.application.domain import Customer
from app.application.ports import CustomersGateway
from app.infrastructure.data_mapper import (
    InMemoryCustomersDataMapper,
    PostgreSQLCustomersDataMapper,
)
from app.infrastructure.data_mapper.customers import _get_customers


class FakeCursor:
    def __init__(self, rows: list[TupleRow]) -> None:
        self._rows = rows
        self.parameters: tuple[int, int] | None = None

    async def execute(self, query: object, parameters: tuple[int, int]) -> None:
        self.parameters = parameters

    async def fetchall(self) -> list[TupleRow]:
        return self._rows


@pytest.mark.anyio
async def test_in_memory_customers_data_mapper_paginates_customers() -> None:
    gateway: CustomersGateway = InMemoryCustomersDataMapper()

    customers = await gateway.get_customers(limit=1, offset=1)

    assert customers == [
        Customer(
            id=2,
            login="second-customer",
            email="second.customer@example.com",
            business_name="Second Business",
            business_contact_name="Second Contact",
            preferred_language="en",
        )
    ]

@pytest.mark.anyio
async def test_in_memory_customers_data_mapper_rejects_invalid_pagination() -> None:
    gateway = InMemoryCustomersDataMapper()

    with pytest.raises(ValueError, match="limit must be greater than 0"):
        await gateway.get_customers(limit=0)

    with pytest.raises(ValueError, match="offset must be greater than or equal to 0"):
        await gateway.get_customers(offset=-1)


@pytest.mark.anyio
async def test_postgresql_customer_query_maps_rows_and_normalizes_json() -> None:
    cursor = FakeCursor(
        [
            (
                42,
                "customer-login",
                "customer@example.com",
                "Example Business",
                "Example Contact",
                None,
                None,
                {"newsletter": True},
                None,
            )
        ]
    )

    customers = await _get_customers(
        cast(psycopg.AsyncCursor[TupleRow], cursor),
        limit=25,
        offset=50,
    )

    assert cursor.parameters == (25, 50)
    assert customers == [
        Customer(
            id=42,
            login="customer-login",
            email="customer@example.com",
            business_name="Example Business",
            business_contact_name="Example Contact",
            extra_data={},
            parameters={"newsletter": True},
        )
    ]


@pytest.mark.anyio
async def test_postgresql_customers_data_mapper_rejects_invalid_pagination() -> None:
    gateway: CustomersGateway = PostgreSQLCustomersDataMapper(
        "postgresql://localhost/test"
    )

    with pytest.raises(ValueError, match="limit must be greater than 0"):
        await gateway.get_customers(limit=0)

    with pytest.raises(ValueError, match="offset must be greater than or equal to 0"):
        await gateway.get_customers(offset=-1)
