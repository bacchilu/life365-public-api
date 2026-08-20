from datetime import datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.api.dependencies import get_current_user
from app.application.domain import AuthenticatedUser, Order, OrderDetail
from app.application.ports import OrdersGateway
from app.application.services.order_service import OrderService
from app.infrastructure.data_mapper import DATABASE_URL, PostgreSQLOrdersDataMapper

router: APIRouter = APIRouter(tags=["orders"])
orders_gateway: OrdersGateway = PostgreSQLOrdersDataMapper(DATABASE_URL)
order_service: OrderService = OrderService(orders_gateway)


class OrderDetailResponse(BaseModel):
    id: int
    product_id: int
    product_stock_id: int
    isin: str
    description: str
    quantity: int
    unit_price: Decimal


class OrderResponse(BaseModel):
    id: int
    customer_id: int
    order_date: datetime
    logistic_state: str
    financial_state: str
    total: Decimal | None
    customer_reference: str | None
    details: list[OrderDetailResponse]


def _order_detail_to_response(detail: OrderDetail) -> OrderDetailResponse:
    return OrderDetailResponse(
        id=detail.id,
        product_id=detail.product_id,
        product_stock_id=detail.product_stock_id,
        isin=detail.isin,
        description=detail.description,
        quantity=detail.quantity,
        unit_price=detail.unit_price,
    )


def _order_to_response(order: Order) -> OrderResponse:
    return OrderResponse(
        id=order.id,
        customer_id=order.customer_id,
        order_date=order.order_date,
        logistic_state=order.logistic_state,
        financial_state=order.financial_state,
        total=order.total,
        customer_reference=order.customer_reference,
        details=[_order_detail_to_response(detail) for detail in order.details],
    )


@router.get(
    "/orders",
    summary="List final orders",
    response_model=list[OrderResponse],
)
async def get_orders(
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[OrderResponse]:
    """
    Retrieve a paginated list of delivered orders and their detail lines.

    Orders are read from PostgreSQL and ordered from newest to oldest by ID.
    Only orders whose current logistic state is `DELIVERED` are returned;
    financial state remains independent and may be `PAID` or `UNPAID`.
    """
    orders: list[Order] = await order_service.get_orders(limit=limit, offset=offset)
    return [_order_to_response(order) for order in orders]
