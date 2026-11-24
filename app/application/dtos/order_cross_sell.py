"""Data used to send post-order recommendations to Salesforce Marketing."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OrderCrossSellState:
    customer_id: int | None
    logistic_state: str | None
    invoice_number: int | None


@dataclass(frozen=True, slots=True)
class OrderCrossSellRequest:
    order_id: int
    customer_id: int
    product_ids: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class OrderCrossSellReceipt:
    record_ids: tuple[str, ...]
