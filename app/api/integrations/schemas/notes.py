"""Customer note fields for the version 1 create request."""

from datetime import datetime
from re import fullmatch

from pydantic import AwareDatetime, Field, StrictBool, StrictStr, field_validator

from app.api.integrations.schemas.base import IntegrationRequestModel


class IntegrationCustomerNote(IntegrationRequestModel):
    occurred_at: AwareDatetime = Field(alias="occurredAt")
    text: StrictStr
    open: StrictBool

    @field_validator("occurred_at", mode="before")
    @classmethod
    def validate_timestamp_format(cls, value: object) -> object:
        if isinstance(value, datetime):
            return value
        if isinstance(value, str) and fullmatch(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}[Tt][0-9]{2}:[0-9]{2}:[0-9]{2}"
            r"(?:\.[0-9]+)?(?:[Zz]|[+-][0-9]{2}:[0-9]{2})",
            value,
        ):
            return value
        raise ValueError("Date-time must be an RFC 3339 string with a UTC offset")


class IntegrationCustomerNotes(IntegrationRequestModel):
    items: list[IntegrationCustomerNote] = Field(strict=True)
    administrative_note: StrictStr | None = Field(
        alias="administrativeNote", max_length=250
    )
