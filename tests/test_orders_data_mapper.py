from datetime import datetime
from decimal import Decimal
from typing import cast

import psycopg
import pytest
from psycopg.rows import TupleRow

from app.application.domain import Order, OrderDetail
from app.application.ports import OrdersGateway
from app.infrastructure.data_mapper import (
    InMemoryOrdersDataMapper,
    PostgreSQLOrdersDataMapper,
)
from app.infrastructure.data_mapper.orders import (
    QUALIFYING_LOGISTIC_STATES,
    _get_orders,
)


class FakeCursor:
    def __init__(self, result_sets: list[list[TupleRow]]) -> None:
        self._result_sets = result_sets
        self.parameters: list[tuple[object, ...]] = []

    async def execute(self, query: object, parameters: tuple[object, ...]) -> None:
        self.parameters.append(parameters)

    async def fetchall(self) -> list[TupleRow]:
        return self._result_sets.pop(0)


@pytest.mark.anyio
async def test_in_memory_orders_data_mapper_paginates_final_orders() -> None:
    gateway: OrdersGateway = InMemoryOrdersDataMapper()

    orders: list[Order] = await gateway.get_orders(limit=1, offset=1)

    assert len(orders) == 1
    assert orders[0].id == 1002
    assert orders[0].logistic_state == "DELIVERED"


@pytest.mark.anyio
async def test_in_memory_orders_data_mapper_rejects_invalid_pagination() -> None:
    gateway: OrdersGateway = InMemoryOrdersDataMapper()

    with pytest.raises(ValueError, match="limit must be greater than 0"):
        await gateway.get_orders(limit=0)

    with pytest.raises(ValueError, match="offset must be greater than or equal to 0"):
        await gateway.get_orders(offset=-1)


@pytest.mark.anyio
async def test_postgresql_order_query_maps_headers_and_nested_details() -> None:
    order_date = datetime(2026, 8, 20, 10, 30)
    cursor = FakeCursor(
        [
            [
                (
                    42,
                    9,
                    order_date,
                    "DELIVERED",
                    "PAID",
                    Decimal("25.00"),
                    "CUSTOMER-REFERENCE",
                )
            ],
            [
                (
                    101,
                    42,
                    201,
                    301,
                    "PRODUCT-CODE",
                    "Product description",
                    2,
                    Decimal("12.50"),
                )
            ],
        ]
    )

    orders = await _get_orders(
        cast(psycopg.AsyncCursor[TupleRow], cursor),
        limit=25,
        offset=50,
    )

    assert cursor.parameters == [
        (list(QUALIFYING_LOGISTIC_STATES), 25, 50),
        ([42],),
    ]
    assert orders == [
        Order(
            id=42,
            customer_id=9,
            order_date=order_date,
            logistic_state="DELIVERED",
            financial_state="PAID",
            total=Decimal("25.00"),
            customer_reference="CUSTOMER-REFERENCE",
            details=(
                OrderDetail(
                    id=101,
                    product_id=201,
                    product_stock_id=301,
                    isin="PRODUCT-CODE",
                    description="Product description",
                    quantity=2,
                    unit_price=Decimal("12.50"),
                ),
            ),
        )
    ]


@pytest.mark.anyio
async def test_postgresql_orders_data_mapper_rejects_invalid_pagination() -> None:
    gateway: OrdersGateway = PostgreSQLOrdersDataMapper(
        "postgresql://localhost/test"
    )

    with pytest.raises(ValueError, match="limit must be greater than 0"):
        await gateway.get_orders(limit=0)

    with pytest.raises(ValueError, match="offset must be greater than or equal to 0"):
        await gateway.get_orders(offset=-1)
