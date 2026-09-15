"""Partial tax and banking updates; UNSET leaves a field unchanged."""

from dataclasses import dataclass
from decimal import Decimal

from app.application.dtos.customer_integration.unset import UNSET, UnsetType


@dataclass(frozen=True, slots=True)
class IntegrationTaxProfilePatch:
    fiscal_code: str | None | UnsetType = UNSET
    vat_country_code: str | None | UnsetType = UNSET
    vat_number: str | None | UnsetType = UNSET
    vies_validated: bool | UnsetType = UNSET
    fiscal_agent_code: str | None | UnsetType = UNSET
    secondary_tax_value: Decimal | None | UnsetType = UNSET

    def __post_init__(self) -> None:
        if self.vies_validated is None:
            raise ValueError("taxProfile.viesValidated cannot be cleared")


@dataclass(frozen=True, slots=True)
class IntegrationBankingPatch:
    abi: str | None | UnsetType = UNSET
    cab: str | None | UnsetType = UNSET
    iban: str | None | UnsetType = UNSET
