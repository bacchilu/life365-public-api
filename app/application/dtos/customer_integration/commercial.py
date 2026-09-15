"""Commercial values used by the customer integration contract."""

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class IntegrationCategory:
    code: str
    label: str


@dataclass(frozen=True, slots=True)
class IntegrationSalesChannel:
    code: str
    label: str


@dataclass(frozen=True, slots=True)
class IntegrationAgent:
    reference_id: int
    user_login: str
    name: str
    email: str
    phone: str | None


@dataclass(frozen=True, slots=True)
class IntegrationCommercial:
    preferred_categories: tuple[IntegrationCategory, ...]
    sales_channel: IntegrationSalesChannel | None
    assigned_agent: IntegrationAgent | None
    payment_agreement: str | None
    preferred_payment_type_code: str | None
    payment_days: int | None
    payment_days_end_of_month: int | None
    credit_granted: Decimal | None
    credit_value: Decimal | None
