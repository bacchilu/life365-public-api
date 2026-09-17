"""Partial customer profile fields for version 1 update requests."""

from datetime import datetime
from re import fullmatch
from typing import Annotated

from pydantic import (
    AwareDatetime,
    Field,
    StrictBool,
    StringConstraints,
    field_validator,
)

from app.api.integrations.schemas.base import IntegrationRequestModel
from app.api.integrations.schemas.profile import IntegrationAdditionalEmail
from app.application.dtos.customer_integration.unset import UNSET, UnsetType

PatchString = Annotated[
    str,
    StringConstraints(strict=True),
]
BoundedPatchString = Annotated[
    str,
    StringConstraints(strict=True, min_length=1, max_length=50),
]
StrictAdditionalEmails = Annotated[
    list[IntegrationAdditionalEmail],
    Field(strict=True),
]


class IntegrationCustomerCredentialsPatch(IntegrationRequestModel):
    login: BoundedPatchString | UnsetType = UNSET
    password: BoundedPatchString | UnsetType = Field(default=UNSET, repr=False)

    @field_validator("login", "password")
    @classmethod
    def reject_null_credentials(cls, value: object) -> object:
        if value is None:
            raise ValueError("Credential fields cannot be cleared")
        return value


class IntegrationCompanyPatch(IntegrationRequestModel):
    name: Annotated[str, StringConstraints(strict=True, max_length=120)] | UnsetType = (
        UNSET
    )
    website: (
        Annotated[str, StringConstraints(strict=True, max_length=100)]
        | None
        | UnsetType
    ) = UNSET
    primary_phone: (
        Annotated[str, StringConstraints(strict=True, max_length=50)] | None | UnsetType
    ) = Field(default=UNSET, alias="primaryPhone")
    secondary_phone: (
        Annotated[str, StringConstraints(strict=True, max_length=50)] | None | UnsetType
    ) = Field(default=UNSET, alias="secondaryPhone")

    @field_validator("name")
    @classmethod
    def reject_null_company_name(cls, value: object) -> object:
        if value is None:
            raise ValueError("company.name cannot be cleared")
        return value


class IntegrationPrimaryContactPatch(IntegrationRequestModel):
    full_name: (
        Annotated[str, StringConstraints(strict=True, max_length=100)] | UnsetType
    ) = Field(default=UNSET, alias="fullName")
    email: (
        Annotated[str, StringConstraints(strict=True, max_length=120)] | UnsetType
    ) = UNSET
    additional_emails: StrictAdditionalEmails | UnsetType = Field(
        default=UNSET, alias="additionalEmails"
    )
    certified_email: PatchString | None | UnsetType = Field(
        default=UNSET, alias="certifiedEmail"
    )
    preferred_language: PatchString | None | UnsetType = Field(
        default=UNSET, alias="preferredLanguage"
    )

    @field_validator("full_name", "email", "additional_emails")
    @classmethod
    def reject_null_required_contact_fields(cls, value: object) -> object:
        if value is None:
            raise ValueError("Required contact fields cannot be cleared")
        return value


class IntegrationCommunicationPreferencesPatch(IntegrationRequestModel):
    newsletter: StrictBool | None | UnsetType = UNSET
    privacy_registered: StrictBool | None | UnsetType = Field(
        default=UNSET, alias="privacyRegistered"
    )
    rules_registered: StrictBool | None | UnsetType = Field(
        default=UNSET, alias="rulesRegistered"
    )


class IntegrationRegistrationPatch(IntegrationRequestModel):
    registered_at: AwareDatetime | None | UnsetType = Field(
        default=UNSET, alias="registeredAt"
    )
    verified: StrictBool | None | UnsetType = UNSET
    last_login_at: AwareDatetime | None | UnsetType = Field(
        default=UNSET, alias="lastLoginAt"
    )

    @field_validator("registered_at", "last_login_at", mode="before")
    @classmethod
    def validate_timestamp_format(cls, value: object) -> object:
        if value is None or value is UNSET or isinstance(value, datetime):
            return value
        if isinstance(value, str) and fullmatch(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}[Tt][0-9]{2}:[0-9]{2}:[0-9]{2}"
            r"(?:\.[0-9]+)?(?:[Zz]|[+-][0-9]{2}:[0-9]{2})",
            value,
        ):
            return value
        raise ValueError("Date-time must be an RFC 3339 string with a UTC offset")
