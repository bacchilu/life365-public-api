"""Partial commercial updates; UNSET leaves a field unchanged."""

from dataclasses import dataclass
from decimal import Decimal

from app.application.dtos.customer_integration.commercial import (
    IntegrationAgent,
    IntegrationCategory,
)
from app.application.dtos.customer_integration.unset import UNSET, UnsetType


@dataclass(frozen=True, slots=True)
class IntegrationSalesChannelPatch:
    code: str | UnsetType = UNSET
    label: str | UnsetType = UNSET

    def __post_init__(self) -> None:
        if self.code is None:
            raise ValueError("commercial.salesChannel.code cannot be cleared")
        if self.label is None:
            raise ValueError("commercial.salesChannel.label cannot be cleared")


@dataclass(frozen=True, slots=True)
class IntegrationCommercialPatch:
    """Supplied categories replace the complete list; () clears it.

    A supplied agent is a complete reference object. None requests Life365's
    fallback-agent policy. A supplied sales channel patches its nested fields.
    """

    preferred_categories: tuple[IntegrationCategory, ...] | UnsetType = UNSET
    sales_channel: IntegrationSalesChannelPatch | None | UnsetType = UNSET
    assigned_agent: IntegrationAgent | None | UnsetType = UNSET
    payment_agreement: str | None | UnsetType = UNSET
    preferred_payment_type_code: str | None | UnsetType = UNSET
    payment_days: int | None | UnsetType = UNSET
    payment_days_end_of_month: int | None | UnsetType = UNSET
    credit_granted: Decimal | None | UnsetType = UNSET
    credit_value: Decimal | None | UnsetType = UNSET

    def __post_init__(self) -> None:
        if self.preferred_categories is None:
            raise ValueError(
                "commercial.preferredCategories cannot be cleared with null"
            )
