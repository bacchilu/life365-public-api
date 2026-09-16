"""Shop and operational fields for the version 1 create request."""

from decimal import Decimal
from typing import Annotated

from pydantic import Field, StrictBool, StrictStr, StringConstraints, field_validator

from app.api.integrations.schemas.base import IntegrationRequestModel

Coordinate = Annotated[float, Field(strict=True, allow_inf_nan=False)]

NonEmptyString = Annotated[str, StringConstraints(strict=True, min_length=1)]


class IntegrationShopGroup(IntegrationRequestModel):
    code: NonEmptyString
    label: StrictStr = Field(min_length=1, max_length=50)


class IntegrationShop(IntegrationRequestModel):
    latitude: Coordinate | None = Field(ge=-90, le=90)
    longitude: Coordinate | None = Field(ge=-180, le=180)
    groups: list[IntegrationShopGroup] = Field(strict=True)

    @field_validator("latitude", "longitude")
    @classmethod
    def validate_coordinate_scale(cls, value: float | None) -> float | None:
        if value is None:
            return value
        if Decimal(str(value)).as_tuple().exponent < -10:
            raise ValueError("Coordinates can have at most 10 decimal places")
        return value


class IntegrationOperationalSettings(IntegrationRequestModel):
    disable_box_discount: StrictBool = Field(alias="disableBoxDiscount")
    disable_quantity_delivery: StrictBool | None = Field(
        alias="disableQuantityDelivery"
    )
    prepaid_returns: StrictBool | None = Field(alias="prepaidReturns")
    disable_sale_limit: StrictBool | None = Field(alias="disableSaleLimit")
