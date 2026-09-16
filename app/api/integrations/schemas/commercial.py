"""Commercial fields for the version 1 create request."""

from typing import Annotated

from pydantic import Field, StrictInt, StrictStr, StringConstraints

from app.api.integrations.schemas.base import IntegrationRequestModel

CreditDecimalString = Annotated[
    str,
    StringConstraints(
        strict=True,
        pattern=r"^-?[0-9]{1,8}\.[0-9]{2}$",
    ),
]

NonEmptyString = Annotated[
    str,
    StringConstraints(strict=True, min_length=1),
]


class IntegrationCategory(IntegrationRequestModel):
    code: NonEmptyString
    label: NonEmptyString


class IntegrationSalesChannel(IntegrationRequestModel):
    code: NonEmptyString
    label: StrictStr = Field(min_length=1, max_length=250)


class IntegrationAgent(IntegrationRequestModel):
    reference_id: Annotated[StrictInt, Field(alias="referenceId", gt=0)]
    user_login: StrictStr = Field(alias="userLogin", min_length=1, max_length=20)
    name: StrictStr = Field(min_length=1, max_length=30)
    email: StrictStr = Field(min_length=1, max_length=50)
    phone: StrictStr | None = Field(max_length=50)


class IntegrationCommercial(IntegrationRequestModel):
    preferred_categories: list[IntegrationCategory] = Field(
        alias="preferredCategories",
        strict=True,
    )
    sales_channel: IntegrationSalesChannel | None = Field(alias="salesChannel")
    assigned_agent: IntegrationAgent | None = Field(alias="assignedAgent")
    payment_agreement: StrictStr | None = Field(
        alias="paymentAgreement",
        max_length=100,
    )
    preferred_payment_type_code: StrictStr | None = Field(
        alias="preferredPaymentTypeCode",
        max_length=50,
    )
    payment_days: StrictInt | None = Field(alias="paymentDays")
    payment_days_end_of_month: StrictInt | None = Field(alias="paymentDaysEndOfMonth")
    credit_granted: CreditDecimalString | None = Field(alias="creditGranted")
    credit_value: CreditDecimalString | None = Field(alias="creditValue")
