"""Convert complete API customer data and patches to application DTOs."""

from collections.abc import Callable
from typing import TypeVar

from app.api.integrations.converters.address import (
    convert_address,
    convert_address_patch,
    convert_delivery,
    convert_delivery_patch,
)
from app.api.integrations.converters.commercial import (
    convert_commercial,
    convert_commercial_patch,
)
from app.api.integrations.converters.finance import (
    convert_banking,
    convert_banking_patch,
    convert_tax_profile,
    convert_tax_profile_patch,
)
from app.api.integrations.converters.operations import (
    convert_customer_extensions_patch,
    convert_customer_notes_patch,
    convert_extensions,
    convert_notes,
    convert_operational_settings,
    convert_operational_settings_patch,
    convert_shop,
    convert_shop_patch,
)
from app.api.integrations.converters.profile import (
    convert_communication_preferences,
    convert_communication_preferences_patch,
    convert_company,
    convert_company_patch,
    convert_credentials,
    convert_credentials_patch,
    convert_primary_contact,
    convert_primary_contact_patch,
    convert_registration,
    convert_registration_patch,
)
from app.api.integrations.schemas.customer import (
    IntegrationCustomerData as ApiCustomerData,
)
from app.api.integrations.schemas.customer_patch import (
    CustomerUpdatedData as ApiCustomerUpdatedData,
)
from app.application.dtos.customer_integration.customer import (
    IntegrationCustomerData,
)
from app.application.dtos.customer_integration.customer_patch import (
    CustomerUpdatedData,
)
from app.application.dtos.customer_integration.unset import UNSET, UnsetType

_Source = TypeVar("_Source")
_Target = TypeVar("_Target")


def _convert_patch_section(
    source: _Source | UnsetType,
    converter: Callable[[_Source], _Target],
) -> _Target | UnsetType:
    if isinstance(source, UnsetType):
        return UNSET
    return converter(source)


def convert_customer_data(source: ApiCustomerData) -> IntegrationCustomerData:
    return IntegrationCustomerData(
        credentials=convert_credentials(source.credentials),
        company=convert_company(source.company),
        primary_contact=convert_primary_contact(source.primary_contact),
        billing_address=convert_address(source.billing_address),
        delivery=convert_delivery(source.delivery),
        tax_profile=convert_tax_profile(source.tax_profile),
        communication_preferences=convert_communication_preferences(
            source.communication_preferences
        ),
        registration=convert_registration(source.registration),
        commercial=convert_commercial(source.commercial),
        banking=convert_banking(source.banking),
        shop=convert_shop(source.shop),
        operational_settings=convert_operational_settings(
            source.operational_settings
        ),
        notes=convert_notes(source.notes),
        extensions=convert_extensions(source.extensions),
    )


def convert_customer_patch(
    source: ApiCustomerUpdatedData,
) -> CustomerUpdatedData:
    return CustomerUpdatedData(
        credentials=_convert_patch_section(
            source.credentials, convert_credentials_patch
        ),
        company=_convert_patch_section(source.company, convert_company_patch),
        primary_contact=_convert_patch_section(
            source.primary_contact, convert_primary_contact_patch
        ),
        billing_address=_convert_patch_section(
            source.billing_address, convert_address_patch
        ),
        delivery=_convert_patch_section(source.delivery, convert_delivery_patch),
        tax_profile=_convert_patch_section(
            source.tax_profile, convert_tax_profile_patch
        ),
        communication_preferences=_convert_patch_section(
            source.communication_preferences,
            convert_communication_preferences_patch,
        ),
        registration=_convert_patch_section(
            source.registration, convert_registration_patch
        ),
        commercial=_convert_patch_section(
            source.commercial, convert_commercial_patch
        ),
        banking=_convert_patch_section(source.banking, convert_banking_patch),
        shop=_convert_patch_section(source.shop, convert_shop_patch),
        operational_settings=_convert_patch_section(
            source.operational_settings,
            convert_operational_settings_patch,
        ),
        notes=_convert_patch_section(source.notes, convert_customer_notes_patch),
        extensions=_convert_patch_section(
            source.extensions, convert_customer_extensions_patch
        ),
    )
