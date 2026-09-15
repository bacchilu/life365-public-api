"""Tax and banking values used by the customer integration contract."""

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class IntegrationTaxProfile:
    fiscal_code: str | None
    vat_country_code: str | None
    vat_number: str | None
    vies_validated: bool
    fiscal_agent_code: str | None
    secondary_tax_value: Decimal | None


@dataclass(frozen=True, slots=True)
class IntegrationBanking:
    abi: str | None
    cab: str | None
    iban: str | None
