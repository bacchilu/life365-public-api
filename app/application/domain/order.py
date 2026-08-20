from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class OrderDetail:
    id: int
    product_id: int
    product_stock_id: int
    isin: str
    description: str
    quantity: int
    unit_price: Decimal


@dataclass(frozen=True, slots=True)
class Order:
    id: int
    customer_id: int
    order_date: datetime
    logistic_state: str
    financial_state: str
    total: Decimal | None
    customer_reference: str | None
    details: tuple[OrderDetail, ...]
