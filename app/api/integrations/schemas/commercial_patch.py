"""Partial commercial fields for version 1 update requests."""

from typing import Annotated

from pydantic import Field, StrictInt, StrictStr, StringConstraints

from app.api.integrations.schemas.base import IntegrationRequestModel
from app.api.integrations.schemas.commercial import (
    CreditDecimalString,
    IntegrationAgent,
    IntegrationCategory,
)
from app.application.dtos.customer_integration.unset import UNSET, UnsetType

StrictCategories = Annotated[list[IntegrationCategory], Field(strict=True)]


class IntegrationSalesChannelPatch(IntegrationRequestModel):
    code: StrictStr | UnsetType = UNSET
    label: (
        Annotated[str, StringConstraints(strict=True, max_length=250)] | UnsetType
    ) = UNSET


class IntegrationCommercialPatch(IntegrationRequestModel):
    preferred_categories: StrictCategories | UnsetType = Field(
        default=UNSET, alias="preferredCategories"
    )
    sales_channel: IntegrationSalesChannelPatch | None | UnsetType = Field(
        default=UNSET, alias="salesChannel"
    )
    assigned_agent: IntegrationAgent | None | UnsetType = Field(
        default=UNSET, alias="assignedAgent"
    )
    payment_agreement: (
        Annotated[str, StringConstraints(strict=True, max_length=100)]
        | None
        | UnsetType
    ) = Field(default=UNSET, alias="paymentAgreement")
    preferred_payment_type_code: (
        Annotated[str, StringConstraints(strict=True, max_length=50)] | None | UnsetType
    ) = Field(default=UNSET, alias="preferredPaymentTypeCode")
    payment_days: StrictInt | None | UnsetType = Field(
        default=UNSET, alias="paymentDays"
    )
    payment_days_end_of_month: StrictInt | None | UnsetType = Field(
        default=UNSET, alias="paymentDaysEndOfMonth"
    )
    credit_granted: CreditDecimalString | None | UnsetType = Field(
        default=UNSET, alias="creditGranted"
    )
    credit_value: CreditDecimalString | None | UnsetType = Field(
        default=UNSET, alias="creditValue"
    )
