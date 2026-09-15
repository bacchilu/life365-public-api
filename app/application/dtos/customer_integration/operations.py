"""Operational values used by the customer integration contract."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class IntegrationShopGroup:
    code: str
    label: str


@dataclass(frozen=True, slots=True)
class IntegrationShop:
    latitude: float | None
    longitude: float | None
    groups: tuple[IntegrationShopGroup, ...]


@dataclass(frozen=True, slots=True)
class IntegrationOperationalSettings:
    disable_box_discount: bool
    disable_quantity_delivery: bool | None
    prepaid_returns: bool | None
    disable_sale_limit: bool | None


@dataclass(frozen=True, slots=True)
class IntegrationCustomerNote:
    occurred_at: datetime
    text: str
    open: bool


@dataclass(frozen=True, slots=True)
class IntegrationCustomerNotes:
    items: tuple[IntegrationCustomerNote, ...]
    administrative_note: str | None


@dataclass(frozen=True, slots=True)
class IntegrationCustomerExtensions:
    parameters: dict[str, Any] | None
    extra_data: dict[str, Any] | None
