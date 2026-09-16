"""Tax and banking fields for the version 1 create request."""

from typing import Annotated

from pydantic import (
    Field,
    StrictBool,
    StrictStr,
    StringConstraints,
    model_validator,
)

from app.api.integrations.schemas.base import IntegrationRequestModel

TaxDecimalString = Annotated[
    str,
    StringConstraints(
        strict=True,
        pattern=r"^-?[0-9]{1,16}\.[0-9]{2}$",
    ),
]


class IntegrationTaxProfile(IntegrationRequestModel):
    fiscal_code: StrictStr | None = Field(alias="fiscalCode", max_length=20)
    vat_country_code: StrictStr | None = Field(
        alias="vatCountryCode",
        min_length=2,
        max_length=2,
        pattern="^[A-Z]{2}$",
    )
    vat_number: StrictStr | None = Field(alias="vatNumber", max_length=20)
    vies_validated: StrictBool = Field(alias="viesValidated")
    fiscal_agent_code: StrictStr | None = Field(
        alias="fiscalAgentCode",
        max_length=45,
    )
    secondary_tax_value: TaxDecimalString | None = Field(alias="secondaryTaxValue")

    @model_validator(mode="after")
    def require_tax_identity(self) -> "IntegrationTaxProfile":
        fiscal_code = self.fiscal_code.strip() if self.fiscal_code else ""
        vat_number = self.vat_number.strip() if self.vat_number else ""
        if not fiscal_code and not vat_number:
            raise ValueError("Provide fiscalCode or vatNumber")
        return self


class IntegrationBanking(IntegrationRequestModel):
    abi: StrictStr | None = Field(max_length=5)
    cab: StrictStr | None = Field(max_length=5)
    iban: StrictStr | None = Field(max_length=34)
