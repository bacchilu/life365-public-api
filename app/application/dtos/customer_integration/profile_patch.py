"""Partial profile updates; UNSET leaves a field unchanged."""

from dataclasses import dataclass, field
from datetime import datetime

from app.application.dtos.customer_integration.profile import IntegrationAdditionalEmail
from app.application.dtos.customer_integration.unset import UNSET, UnsetType


@dataclass(frozen=True, slots=True)
class IntegrationCustomerCredentialsPatch:
    login: str | UnsetType = UNSET
    password: str | UnsetType = field(default=UNSET, repr=False)

    def __post_init__(self) -> None:
        if self.login is None:
            raise ValueError("credentials.login cannot be cleared")
        if self.password is None:
            raise ValueError("credentials.password cannot be cleared")


@dataclass(frozen=True, slots=True)
class IntegrationCompanyPatch:
    name: str | UnsetType = UNSET
    website: str | None | UnsetType = UNSET
    primary_phone: str | None | UnsetType = UNSET
    secondary_phone: str | None | UnsetType = UNSET

    def __post_init__(self) -> None:
        if self.name is None:
            raise ValueError("company.name cannot be cleared")


@dataclass(frozen=True, slots=True)
class IntegrationPrimaryContactPatch:
    """Supplied additional_emails replaces the complete list; () clears it."""

    full_name: str | UnsetType = UNSET
    email: str | UnsetType = UNSET
    additional_emails: tuple[IntegrationAdditionalEmail, ...] | UnsetType = UNSET
    certified_email: str | None | UnsetType = UNSET
    preferred_language: str | None | UnsetType = UNSET

    def __post_init__(self) -> None:
        if self.full_name is None:
            raise ValueError("primaryContact.fullName cannot be cleared")
        if self.email is None:
            raise ValueError("primaryContact.email cannot be cleared")
        if self.additional_emails is None:
            raise ValueError(
                "primaryContact.additionalEmails cannot be cleared with null"
            )


@dataclass(frozen=True, slots=True)
class IntegrationCommunicationPreferencesPatch:
    newsletter: bool | None | UnsetType = UNSET
    privacy_registered: bool | None | UnsetType = UNSET
    rules_registered: bool | None | UnsetType = UNSET


@dataclass(frozen=True, slots=True)
class IntegrationRegistrationPatch:
    registered_at: datetime | None | UnsetType = UNSET
    verified: bool | None | UnsetType = UNSET
    last_login_at: datetime | None | UnsetType = UNSET
