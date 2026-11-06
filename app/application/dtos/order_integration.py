"""Application contract for synchronous order notifications to Salesforce."""

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from .customer_integration.address import IntegrationAddress

OrderEventType = Literal["order.created", "order.updated", "order.deleted"]


@dataclass(frozen=True, slots=True)
class IntegrationOrderInvoice:
    number: str
    date: date
    url: str | None = None


@dataclass(frozen=True, slots=True)
class IntegrationOrderTotals:
    net: Decimal
    tax: Decimal
    gross: Decimal


@dataclass(frozen=True, slots=True)
class IntegrationOrderLine:
    line_id: str
    product_reference_id: int
    sku: str
    description: str
    quantity: int
    unit_price: Decimal
    line_total: Decimal


@dataclass(frozen=True, slots=True)
class IntegrationOrderData:
    customer_reference_id: int
    order_number: str
    status: str
    order_date: datetime
    invoice: IntegrationOrderInvoice | None
    totals: IntegrationOrderTotals
    shipping_address: IntegrationAddress | None
    notes: str | None
    lines: tuple[IntegrationOrderLine, ...]


@dataclass(frozen=True, slots=True)
class OrderExportEvent:
    event_id: UUID
    occurred_at: datetime
    event_type: OrderEventType
    reference_id: int
    data: IntegrationOrderData | None = None
    schema_version: Literal[1] = field(default=1, init=False)

    def __post_init__(self) -> None:
        if self.event_type not in ("order.created", "order.updated", "order.deleted"):
            raise ValueError("Unsupported order export event type")
        if (self.event_type == "order.deleted") != (self.data is None):
            raise ValueError("Only order.deleted must omit order data")
        if self.occurred_at.utcoffset() is None:
            raise ValueError("Order event timestamp must include a timezone")


@dataclass(frozen=True, slots=True)
class OrderExportResult:
    success: bool
    event_id: UUID
    reference_id: int
    record_id: str
