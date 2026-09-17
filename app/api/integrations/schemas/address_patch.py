"""Partial address and delivery fields for version 1 update requests."""

from typing import Annotated

from pydantic import Field, StringConstraints

from app.api.integrations.schemas.base import IntegrationRequestModel
from app.application.dtos.customer_integration.unset import UNSET, UnsetType

StreetPatch = Annotated[str, StringConstraints(strict=True, max_length=100)]
ShortAddressPatch = Annotated[str, StringConstraints(strict=True, max_length=50)]
CountryCodePatch = Annotated[
    str,
    StringConstraints(strict=True, min_length=2, max_length=2, pattern=r"^[A-Z]{2}$"),
]
RegionNamePatch = Annotated[str, StringConstraints(strict=True)]


class IntegrationAddressPatch(IntegrationRequestModel):
    street: StreetPatch | UnsetType = UNSET
    city: ShortAddressPatch | UnsetType = UNSET
    postal_code: ShortAddressPatch | None | UnsetType = Field(
        default=UNSET, alias="postalCode"
    )
    country_code: CountryCodePatch | UnsetType = Field(
        default=UNSET, alias="countryCode"
    )
    region_name: RegionNamePatch | UnsetType = Field(
        default=UNSET,
        alias="regionName",
        description="Exact Life365 region name for the selected country.",
    )


class IntegrationDeliveryPatch(IntegrationRequestModel):
    business_name: (
        Annotated[str, StringConstraints(strict=True, max_length=120)]
        | None
        | UnsetType
    ) = Field(default=UNSET, alias="businessName")
    contact_name: (
        Annotated[str, StringConstraints(strict=True, max_length=100)]
        | None
        | UnsetType
    ) = Field(default=UNSET, alias="contactName")
    phone: ShortAddressPatch | None | UnsetType = UNSET
    address: IntegrationAddressPatch | None | UnsetType = UNSET
