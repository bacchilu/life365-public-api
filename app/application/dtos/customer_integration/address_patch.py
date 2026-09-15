"""Partial address and delivery updates; UNSET leaves a field unchanged."""

from dataclasses import dataclass

from app.application.dtos.customer_integration.unset import UNSET, UnsetType


@dataclass(frozen=True, slots=True)
class IntegrationAddressPatch:
    street: str | UnsetType = UNSET
    city: str | UnsetType = UNSET
    postal_code: str | None | UnsetType = UNSET
    country_code: str | UnsetType = UNSET
    region_name: str | UnsetType = UNSET

    def __post_init__(self) -> None:
        if self.street is None:
            raise ValueError("address.street cannot be cleared")
        if self.city is None:
            raise ValueError("address.city cannot be cleared")
        if self.country_code is None:
            raise ValueError("address.countryCode cannot be cleared")
        if self.region_name is None:
            raise ValueError("address.regionName cannot be cleared")


@dataclass(frozen=True, slots=True)
class IntegrationDeliveryPatch:
    """A nested address patches its fields; None clears the delivery address."""

    business_name: str | None | UnsetType = UNSET
    contact_name: str | None | UnsetType = UNSET
    phone: str | None | UnsetType = UNSET
    address: IntegrationAddressPatch | None | UnsetType = UNSET
