"""Customer profile fields for the version 1 create request."""

from datetime import datetime
from re import fullmatch
from typing import Annotated

from pydantic import (
    AwareDatetime,
    Field,
    StrictBool,
    StrictStr,
    StringConstraints,
    field_validator,
)

from app.api.integrations.schemas.base import IntegrationRequestModel


class IntegrationCustomerCredentials(IntegrationRequestModel):
    login: Annotated[
        str,
        StringConstraints(
            strict=True, strip_whitespace=True, min_length=1, max_length=50
        ),
    ]
    password: StrictStr = Field(
        min_length=1,
        max_length=50,
        repr=False,
        json_schema_extra={"format": "password", "writeOnly": True},
    )


class IntegrationCompany(IntegrationRequestModel):
    name: StrictStr = Field(max_length=120)
    website: StrictStr | None = Field(max_length=100)
    primary_phone: StrictStr | None = Field(alias="primaryPhone", max_length=50)
    secondary_phone: StrictStr | None = Field(alias="secondaryPhone", max_length=50)


class IntegrationAdditionalEmail(IntegrationRequestModel):
    email: StrictStr
    commercial: StrictBool
    marketing: StrictBool
    skype: StrictStr | None


class IntegrationPrimaryContact(IntegrationRequestModel):
    full_name: StrictStr = Field(alias="fullName", max_length=100)
    email: StrictStr = Field(max_length=120)
    additional_emails: list[IntegrationAdditionalEmail] = Field(
        alias="additionalEmails", strict=True
    )
    certified_email: StrictStr | None = Field(alias="certifiedEmail", max_length=100)
    preferred_language: StrictStr | None = Field(
        alias="preferredLanguage", max_length=50
    )


class IntegrationCommunicationPreferences(IntegrationRequestModel):
    newsletter: StrictBool | None
    privacy_registered: StrictBool | None = Field(alias="privacyRegistered")
    rules_registered: StrictBool | None = Field(alias="rulesRegistered")


class IntegrationRegistration(IntegrationRequestModel):
    registered_at: AwareDatetime | None = Field(alias="registeredAt")
    verified: StrictBool | None
    last_login_at: AwareDatetime | None = Field(alias="lastLoginAt")

    @field_validator("registered_at", "last_login_at", mode="before")
    @classmethod
    def validate_timestamp_format(cls, value: object) -> object:
        if value is None or isinstance(value, datetime):
            return value
        if isinstance(value, str) and fullmatch(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}[Tt][0-9]{2}:[0-9]{2}:[0-9]{2}"
            r"(?:\.[0-9]+)?(?:[Zz]|[+-][0-9]{2}:[0-9]{2})",
            value,
        ):
            return value
        raise ValueError("Date-time must be an RFC 3339 string with a UTC offset")
