"""Partial operational updates; UNSET leaves a field unchanged."""

from dataclasses import dataclass
from typing import Any

from app.application.dtos.customer_integration.operations import (
    IntegrationCustomerNote,
    IntegrationShopGroup,
)
from app.application.dtos.customer_integration.unset import UNSET, UnsetType


@dataclass(frozen=True, slots=True)
class IntegrationShopPatch:
    """Supplied groups replace the complete list; () clears it."""

    latitude: float | None | UnsetType = UNSET
    longitude: float | None | UnsetType = UNSET
    groups: tuple[IntegrationShopGroup, ...] | UnsetType = UNSET

    def __post_init__(self) -> None:
        if self.groups is None:
            raise ValueError("shop.groups cannot be cleared with null")


@dataclass(frozen=True, slots=True)
class IntegrationOperationalSettingsPatch:
    disable_box_discount: bool | UnsetType = UNSET
    disable_quantity_delivery: bool | None | UnsetType = UNSET
    prepaid_returns: bool | None | UnsetType = UNSET
    disable_sale_limit: bool | None | UnsetType = UNSET

    def __post_init__(self) -> None:
        if self.disable_box_discount is None:
            raise ValueError("operationalSettings.disableBoxDiscount cannot be cleared")


@dataclass(frozen=True, slots=True)
class IntegrationCustomerNotesPatch:
    """Supplied items replace the complete list; () clears it."""

    items: tuple[IntegrationCustomerNote, ...] | UnsetType = UNSET
    administrative_note: str | None | UnsetType = UNSET

    def __post_init__(self) -> None:
        if self.items is None:
            raise ValueError("notes.items cannot be cleared with null")


@dataclass(frozen=True, slots=True)
class IntegrationCustomerExtensionsPatch:
    """Supplied dictionaries carry recursive JSON Merge Patch operations."""

    parameters: dict[str, Any] | None | UnsetType = UNSET
    extra_data: dict[str, Any] | None | UnsetType = UNSET
