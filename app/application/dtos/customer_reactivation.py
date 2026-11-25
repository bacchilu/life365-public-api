"""Data used to send inactive-customer recommendations to Salesforce."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CustomerReactivationRequest:
    customer_id: int
    product_ids: tuple[int, ...]
    follow_up_product_ids: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class CustomerReactivationReceipt:
    record_ids: tuple[str, ...]
