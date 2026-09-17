"""Partial operational fields for version 1 update requests."""

from decimal import Decimal
from typing import Annotated

from pydantic import Field, StrictBool, StringConstraints, field_validator

from app.api.integrations.schemas.base import IntegrationRequestModel
from app.api.integrations.schemas.extensions import JsonObject
from app.api.integrations.schemas.notes import IntegrationCustomerNote
from app.api.integrations.schemas.shop import IntegrationShopGroup
from app.application.dtos.customer_integration.unset import UNSET, UnsetType

LatitudePatch = Annotated[
    float,
    Field(strict=True, allow_inf_nan=False, ge=-90, le=90),
]
LongitudePatch = Annotated[
    float,
    Field(strict=True, allow_inf_nan=False, ge=-180, le=180),
]
StrictShopGroups = Annotated[list[IntegrationShopGroup], Field(strict=True)]
StrictCustomerNotes = Annotated[list[IntegrationCustomerNote], Field(strict=True)]
StrictJsonObject = Annotated[JsonObject, Field(strict=True)]


class IntegrationShopPatch(IntegrationRequestModel):
    latitude: LatitudePatch | None | UnsetType = UNSET
    longitude: LongitudePatch | None | UnsetType = UNSET
    groups: StrictShopGroups | UnsetType = UNSET

    @field_validator("latitude", "longitude")
    @classmethod
    def validate_coordinate_scale(cls, value: object) -> object:
        if value is None or value is UNSET:
            return value
        exponent = Decimal(str(value)).as_tuple().exponent
        if not isinstance(exponent, int) or exponent < -10:
            raise ValueError("Coordinates can have at most 10 decimal places")
        return value


class IntegrationOperationalSettingsPatch(IntegrationRequestModel):
    disable_box_discount: StrictBool | UnsetType = Field(
        default=UNSET,
        alias="disableBoxDiscount",
    )
    disable_quantity_delivery: StrictBool | None | UnsetType = Field(
        default=UNSET,
        alias="disableQuantityDelivery",
    )
    prepaid_returns: StrictBool | None | UnsetType = Field(
        default=UNSET,
        alias="prepaidReturns",
    )
    disable_sale_limit: StrictBool | None | UnsetType = Field(
        default=UNSET,
        alias="disableSaleLimit",
    )


class IntegrationCustomerNotesPatch(IntegrationRequestModel):
    items: StrictCustomerNotes | UnsetType = UNSET
    administrative_note: (
        Annotated[
            str,
            StringConstraints(strict=True, max_length=250),
        ]
        | None
        | UnsetType
    ) = Field(default=UNSET, alias="administrativeNote")


class IntegrationCustomerExtensionsPatch(IntegrationRequestModel):
    parameters: StrictJsonObject | None | UnsetType = UNSET
    extra_data: StrictJsonObject | None | UnsetType = Field(
        default=UNSET,
        alias="extraData",
    )
