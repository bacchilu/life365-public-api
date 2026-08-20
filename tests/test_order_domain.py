from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.application.domain import Order, OrderDetail


def _order() -> Order:
    return Order(
        id=1,
        customer_id=2,
        order_date=datetime(2026, 8, 1, tzinfo=timezone.utc),
        logistic_state="DELIVERED",
        financial_state="PAID",
        total=Decimal("10.00"),
        customer_reference=None,
        details=(
            OrderDetail(
                id=3,
                product_id=4,
                product_stock_id=5,
                isin="PRODUCT-CODE",
                description="Product description",
                quantity=1,
                unit_price=Decimal("10.00"),
            ),
        ),
    )


def test_order_contains_immutable_detail_entities() -> None:
    order = _order()

    assert order.details[0].product_id == 4

    with pytest.raises(FrozenInstanceError):
        order.logistic_state = "IN-TRANSIT"

    with pytest.raises(FrozenInstanceError):
        order.details[0].quantity = 2
