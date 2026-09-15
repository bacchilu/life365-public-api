"""Customer profile values used by the integration contract."""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True, slots=True)
class IntegrationCustomerCredentials:
    login: str
    password: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class IntegrationCompany:
    name: str
    website: str | None
    primary_phone: str | None
    secondary_phone: str | None


@dataclass(frozen=True, slots=True)
class IntegrationAdditionalEmail:
    email: str
    commercial: bool
    marketing: bool
    skype: str | None


@dataclass(frozen=True, slots=True)
class IntegrationPrimaryContact:
    full_name: str
    email: str
    additional_emails: tuple[IntegrationAdditionalEmail, ...]
    certified_email: str | None
    preferred_language: str | None


@dataclass(frozen=True, slots=True)
class IntegrationCommunicationPreferences:
    newsletter: bool | None
    privacy_registered: bool | None
    rules_registered: bool | None


@dataclass(frozen=True, slots=True)
class IntegrationRegistration:
    registered_at: datetime | None
    verified: bool | None
    last_login_at: datetime | None
