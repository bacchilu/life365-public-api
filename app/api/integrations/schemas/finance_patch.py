"""Partial tax and banking fields for version 1 update requests."""

from typing import Annotated

from pydantic import Field, StrictBool, StringConstraints

from app.api.integrations.schemas.base import IntegrationRequestModel
from app.api.integrations.schemas.finance import TaxDecimalString
from app.application.dtos.customer_integration.unset import UNSET, UnsetType

TaxIdentifierPatch = Annotated[str, StringConstraints(strict=True, max_length=20)]
VatCountryCodePatch = Annotated[
    str,
    StringConstraints(strict=True, min_length=2, max_length=2, pattern=r"^[A-Z]{2}$"),
]
FiscalAgentCodePatch = Annotated[str, StringConstraints(strict=True, max_length=45)]


class IntegrationTaxProfilePatch(IntegrationRequestModel):
    fiscal_code: TaxIdentifierPatch | None | UnsetType = Field(
        default=UNSET, alias="fiscalCode"
    )
    vat_country_code: VatCountryCodePatch | None | UnsetType = Field(
        default=UNSET, alias="vatCountryCode"
    )
    vat_number: TaxIdentifierPatch | None | UnsetType = Field(
        default=UNSET, alias="vatNumber"
    )
    vies_validated: StrictBool | UnsetType = Field(default=UNSET, alias="viesValidated")
    fiscal_agent_code: FiscalAgentCodePatch | None | UnsetType = Field(
        default=UNSET, alias="fiscalAgentCode"
    )
    secondary_tax_value: TaxDecimalString | None | UnsetType = Field(
        default=UNSET, alias="secondaryTaxValue"
    )


class IntegrationBankingPatch(IntegrationRequestModel):
    abi: (
        Annotated[str, StringConstraints(strict=True, max_length=5)] | None | UnsetType
    ) = UNSET
    cab: (
        Annotated[str, StringConstraints(strict=True, max_length=5)] | None | UnsetType
    ) = UNSET
    iban: (
        Annotated[str, StringConstraints(strict=True, max_length=34)] | None | UnsetType
    ) = UNSET
