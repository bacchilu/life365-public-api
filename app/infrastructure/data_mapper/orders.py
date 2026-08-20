from datetime import datetime, timezone
from decimal import Decimal

import psycopg
from psycopg import sql
from psycopg.rows import TupleRow

from app.application.domain import Order, OrderDetail
from app.application.ports import OrdersGateway
from app.infrastructure.data_mapper.connection import get_cursor_context

QUALIFYING_LOGISTIC_STATES: tuple[str, ...] = (
    "CONFIRMED",
    "DELIVERED",
    "UNDELIVERABLE",
)

ORDERS_QUERY = sql.SQL(
    """
    SELECT
        id,
        customer_id,
        order_date,
        logistic_state,
        financial_state,
        total,
        customer_reference
    FROM public.orders
    WHERE logistic_state = ANY(%s)
    ORDER BY id DESC
    LIMIT %s OFFSET %s
    """
)

ORDER_DETAILS_QUERY = sql.SQL(
    """
    SELECT
        od.id,
        od.order_id,
        ps.product_id,
        od.product_stock_id,
        p.isin,
        od.product_description,
        od.qty,
        od.price
    FROM public.order_details AS od
    INNER JOIN public.product_stocks AS ps
        ON ps.id = od.product_stock_id
    INNER JOIN public.products AS p
        ON p.id = ps.product_id
    WHERE od.order_id = ANY(%s)
    ORDER BY od.order_id, od.id
    """
)


def _order_detail_from_row(row: TupleRow) -> tuple[int, OrderDetail]:
    return (
        row[1],
        OrderDetail(
            id=row[0],
            product_id=row[2],
            product_stock_id=row[3],
            isin=row[4],
            description=row[5],
            quantity=row[6],
            unit_price=row[7],
        ),
    )


def _order_from_row(row: TupleRow, details: tuple[OrderDetail, ...]) -> Order:
    return Order(
        id=row[0],
        customer_id=row[1],
        order_date=row[2],
        logistic_state=row[3],
        financial_state=row[4],
        total=row[5],
        customer_reference=row[6],
        details=details,
    )


async def _get_orders(
    cur: psycopg.AsyncCursor[TupleRow], limit: int, offset: int
) -> list[Order]:
    await cur.execute(ORDERS_QUERY, (list(QUALIFYING_LOGISTIC_STATES), limit, offset))
    order_rows: list[TupleRow] = await cur.fetchall()

    if not order_rows:
        return []

    order_ids: list[int] = [row[0] for row in order_rows]
    await cur.execute(ORDER_DETAILS_QUERY, (order_ids,))
    detail_rows: list[TupleRow] = await cur.fetchall()

    details_by_order: dict[int, list[OrderDetail]] = {
        order_id: [] for order_id in order_ids
    }
    for row in detail_rows:
        order_id, detail = _order_detail_from_row(row)
        details_by_order[order_id].append(detail)

    return [_order_from_row(row, tuple(details_by_order[row[0]])) for row in order_rows]


class InMemoryOrdersDataMapper(OrdersGateway):
    def __init__(self) -> None:
        self._orders: tuple[Order, ...] = (
            Order(
                id=1001,
                customer_id=201,
                order_date=datetime(2026, 8, 1, 10, 30, tzinfo=timezone.utc),
                logistic_state="DELIVERED",
                financial_state="PAID",
                total=Decimal("99.80"),
                customer_reference="PO-2026-001",
                details=(
                    OrderDetail(
                        id=5001,
                        product_id=101,
                        product_stock_id=10001,
                        isin="TEST-PRODUCT-001",
                        description="Example medical product",
                        quantity=2,
                        unit_price=Decimal("49.90"),
                    ),
                ),
            ),
            Order(
                id=1002,
                customer_id=202,
                order_date=datetime(2026, 8, 2, 9, 15, tzinfo=timezone.utc),
                logistic_state="DELIVERED",
                financial_state="UNPAID",
                total=Decimal("25.00"),
                customer_reference=None,
                details=(
                    OrderDetail(
                        id=5002,
                        product_id=102,
                        product_stock_id=10002,
                        isin="TEST-PRODUCT-002",
                        description="Second example product",
                        quantity=1,
                        unit_price=Decimal("25.00"),
                    ),
                ),
            ),
        )

    async def get_orders(self, limit: int = 100, offset: int = 0) -> list[Order]:
        if limit < 1:
            raise ValueError("limit must be greater than 0")
        if offset < 0:
            raise ValueError("offset must be greater than or equal to 0")

        return list(self._orders[offset : offset + limit])


class PostgreSQLOrdersDataMapper(OrdersGateway):
    def __init__(self, connection_string: str) -> None:
        self._connection_string = connection_string

    async def get_orders(self, limit: int = 100, offset: int = 0) -> list[Order]:
        if limit < 1:
            raise ValueError("limit must be greater than 0")
        if offset < 0:
            raise ValueError("offset must be greater than or equal to 0")

        async with get_cursor_context(self._connection_string) as cur:
            return await _get_orders(cur, limit=limit, offset=offset)
