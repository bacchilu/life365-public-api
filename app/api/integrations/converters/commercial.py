"""Convert API commercial schemas to application DTOs."""

from decimal import Decimal

from app.api.integrations.schemas import commercial as api_commercial
from app.api.integrations.schemas import commercial_patch as api_patch
from app.application.dtos.customer_integration import (
    commercial as application_commercial,
)
from app.application.dtos.customer_integration import (
    commercial_patch as application_patch,
)
from app.application.dtos.customer_integration.unset import UNSET, UnsetType


def convert_category(
    source: api_commercial.IntegrationCategory,
) -> application_commercial.IntegrationCategory:
    return application_commercial.IntegrationCategory(
        code=source.code,
        label=source.label,
    )


def convert_sales_channel(
    source: api_commercial.IntegrationSalesChannel,
) -> application_commercial.IntegrationSalesChannel:
    return application_commercial.IntegrationSalesChannel(
        code=source.code,
        label=source.label,
    )


def convert_agent(
    source: api_commercial.IntegrationAgent,
) -> application_commercial.IntegrationAgent:
    return application_commercial.IntegrationAgent(
        reference_id=source.reference_id,
        user_login=source.user_login,
        name=source.name,
        email=source.email,
        phone=source.phone,
    )


def convert_commercial(
    source: api_commercial.IntegrationCommercial,
) -> application_commercial.IntegrationCommercial:
    return application_commercial.IntegrationCommercial(
        preferred_categories=tuple(
            convert_category(category) for category in source.preferred_categories
        ),
        sales_channel=(
            convert_sales_channel(source.sales_channel)
            if source.sales_channel is not None
            else None
        ),
        assigned_agent=(
            convert_agent(source.assigned_agent)
            if source.assigned_agent is not None
            else None
        ),
        payment_agreement=source.payment_agreement,
        preferred_payment_type_code=source.preferred_payment_type_code,
        payment_days=source.payment_days,
        payment_days_end_of_month=source.payment_days_end_of_month,
        credit_granted=(
            Decimal(source.credit_granted)
            if source.credit_granted is not None
            else None
        ),
        credit_value=(
            Decimal(source.credit_value) if source.credit_value is not None else None
        ),
    )


def convert_sales_channel_patch(
    source: api_patch.IntegrationSalesChannelPatch,
) -> application_patch.IntegrationSalesChannelPatch:
    return application_patch.IntegrationSalesChannelPatch(
        code=source.code,
        label=source.label,
    )


def _convert_categories_patch(
    source: list[api_commercial.IntegrationCategory] | UnsetType,
) -> tuple[application_commercial.IntegrationCategory, ...] | UnsetType:
    if isinstance(source, UnsetType):
        return UNSET
    return tuple(convert_category(category) for category in source)


def _convert_sales_channel_patch(
    source: api_patch.IntegrationSalesChannelPatch | None | UnsetType,
) -> application_patch.IntegrationSalesChannelPatch | None | UnsetType:
    if isinstance(source, UnsetType):
        return UNSET
    if source is None:
        return None
    return convert_sales_channel_patch(source)


def _convert_agent_patch(
    source: api_commercial.IntegrationAgent | None | UnsetType,
) -> application_commercial.IntegrationAgent | None | UnsetType:
    if isinstance(source, UnsetType):
        return UNSET
    if source is None:
        return None
    return convert_agent(source)


def _convert_decimal_patch(
    source: str | None | UnsetType,
) -> Decimal | None | UnsetType:
    if isinstance(source, UnsetType):
        return UNSET
    return Decimal(source) if source is not None else None


def convert_commercial_patch(
    source: api_patch.IntegrationCommercialPatch,
) -> application_patch.IntegrationCommercialPatch:
    return application_patch.IntegrationCommercialPatch(
        preferred_categories=_convert_categories_patch(source.preferred_categories),
        sales_channel=_convert_sales_channel_patch(source.sales_channel),
        assigned_agent=_convert_agent_patch(source.assigned_agent),
        payment_agreement=source.payment_agreement,
        preferred_payment_type_code=source.preferred_payment_type_code,
        payment_days=source.payment_days,
        payment_days_end_of_month=source.payment_days_end_of_month,
        credit_granted=_convert_decimal_patch(source.credit_granted),
        credit_value=_convert_decimal_patch(source.credit_value),
    )
