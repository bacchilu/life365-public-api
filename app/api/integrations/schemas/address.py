"""Address and delivery fields for the version 1 create request."""

from pydantic import Field, StrictStr

from app.api.integrations.schemas.base import IntegrationRequestModel


class IntegrationAddress(IntegrationRequestModel):
    street: StrictStr = Field(max_length=100)
    city: StrictStr = Field(max_length=50)
    postal_code: StrictStr | None = Field(alias="postalCode", max_length=50)
    country_code: StrictStr = Field(
        alias="countryCode", min_length=2, max_length=2, pattern="^[A-Z]{2}$"
    )
    region_name: StrictStr = Field(
        alias="regionName",
        description="Exact Life365 region name for the selected country.",
    )


class IntegrationDelivery(IntegrationRequestModel):
    business_name: StrictStr | None = Field(alias="businessName", max_length=120)
    contact_name: StrictStr | None = Field(alias="contactName", max_length=100)
    phone: StrictStr | None = Field(max_length=50)
    address: IntegrationAddress | None
