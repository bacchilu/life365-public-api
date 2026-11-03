"""Application contract for the minimal Life365-to-Salesforce product export."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal
from uuid import UUID

ProductEventType = Literal["product.created", "product.updated", "product.deleted"]


@dataclass(frozen=True, slots=True)
class IntegrationProductCategory:
    code: str
    name: str


@dataclass(frozen=True, slots=True)
class IntegrationProductData:
    sku: str
    name: str
    description: str | None
    brand: str | None
    ean: str | None
    category: IntegrationProductCategory | None
    product_url: str
    image_url: str | None
    active: bool


@dataclass(frozen=True, slots=True)
class ProductExportEvent:
    event_id: UUID
    occurred_at: datetime
    event_type: ProductEventType
    reference_id: int
    data: IntegrationProductData | None = None
    schema_version: Literal[1] = field(default=1, init=False)

    def __post_init__(self) -> None:
        if self.event_type not in (
            "product.created",
            "product.updated",
            "product.deleted",
        ):
            raise ValueError("Unsupported product export event type")
        if (self.event_type == "product.deleted") != (self.data is None):
            raise ValueError("Only product.deleted must omit product data")
        if self.occurred_at.utcoffset() is None:
            raise ValueError("Product event timestamp must include a timezone")


@dataclass(frozen=True, slots=True)
class ProductExportResult:
    success: bool
    event_id: UUID
    reference_id: int
    record_id: str
