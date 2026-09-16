"""Extensible JSON fields for the version 1 create request."""

from pydantic import Field, JsonValue

from app.api.integrations.schemas.base import IntegrationRequestModel

JsonObject = dict[str, JsonValue]


class IntegrationCustomerExtensions(IntegrationRequestModel):
    parameters: JsonObject | None = Field(strict=True)
    extra_data: JsonObject | None = Field(alias="extraData", strict=True)
