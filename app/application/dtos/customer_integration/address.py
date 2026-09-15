"""Address and delivery values used by the customer integration contract."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class IntegrationAddress:
    street: str
    city: str
    postal_code: str | None
    country_code: str
    region_name: str


@dataclass(frozen=True, slots=True)
class IntegrationDelivery:
    business_name: str | None
    contact_name: str | None
    phone: str | None
    address: IntegrationAddress | None
