"""Convert API finance schemas to application DTOs."""

from decimal import Decimal

from app.api.integrations.schemas import finance as api_finance
from app.api.integrations.schemas import finance_patch as api_patch
from app.application.dtos.customer_integration import finance as application_finance
from app.application.dtos.customer_integration import (
    finance_patch as application_patch,
)
from app.application.dtos.customer_integration.unset import UNSET, UnsetType


def _convert_optional_decimal(value: str | None) -> Decimal | None:
    return Decimal(value) if value is not None else None


def _convert_decimal_patch(
    value: str | None | UnsetType,
) -> Decimal | None | UnsetType:
    if isinstance(value, UnsetType):
        return UNSET
    return _convert_optional_decimal(value)


def convert_tax_profile(
    source: api_finance.IntegrationTaxProfile,
) -> application_finance.IntegrationTaxProfile:
    return application_finance.IntegrationTaxProfile(
        fiscal_code=source.fiscal_code,
        vat_country_code=source.vat_country_code,
        vat_number=source.vat_number,
        vies_validated=source.vies_validated,
        fiscal_agent_code=source.fiscal_agent_code,
        secondary_tax_value=_convert_optional_decimal(source.secondary_tax_value),
    )


def convert_banking(
    source: api_finance.IntegrationBanking,
) -> application_finance.IntegrationBanking:
    return application_finance.IntegrationBanking(
        abi=source.abi,
        cab=source.cab,
        iban=source.iban,
    )


def convert_tax_profile_patch(
    source: api_patch.IntegrationTaxProfilePatch,
) -> application_patch.IntegrationTaxProfilePatch:
    return application_patch.IntegrationTaxProfilePatch(
        fiscal_code=source.fiscal_code,
        vat_country_code=source.vat_country_code,
        vat_number=source.vat_number,
        vies_validated=source.vies_validated,
        fiscal_agent_code=source.fiscal_agent_code,
        secondary_tax_value=_convert_decimal_patch(source.secondary_tax_value),
    )


def convert_banking_patch(
    source: api_patch.IntegrationBankingPatch,
) -> application_patch.IntegrationBankingPatch:
    return application_patch.IntegrationBankingPatch(
        abi=source.abi,
        cab=source.cab,
        iban=source.iban,
    )
