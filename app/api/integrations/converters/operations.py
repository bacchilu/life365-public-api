"""Convert API operational schemas to application DTOs."""

from app.api.integrations.schemas import extensions as api_extensions
from app.api.integrations.schemas import notes as api_notes
from app.api.integrations.schemas import operations_patch as api_patch
from app.api.integrations.schemas import shop as api_shop
from app.application.dtos.customer_integration import (
    operations as application_operations,
)
from app.application.dtos.customer_integration import (
    operations_patch as application_patch,
)
from app.application.dtos.customer_integration.unset import UNSET, UnsetType


def convert_shop_group(
    source: api_shop.IntegrationShopGroup,
) -> application_operations.IntegrationShopGroup:
    return application_operations.IntegrationShopGroup(
        code=source.code,
        label=source.label,
    )


def convert_shop(
    source: api_shop.IntegrationShop,
) -> application_operations.IntegrationShop:
    return application_operations.IntegrationShop(
        latitude=source.latitude,
        longitude=source.longitude,
        groups=tuple(convert_shop_group(group) for group in source.groups),
    )


def convert_operational_settings(
    source: api_shop.IntegrationOperationalSettings,
) -> application_operations.IntegrationOperationalSettings:
    return application_operations.IntegrationOperationalSettings(
        disable_box_discount=source.disable_box_discount,
        disable_quantity_delivery=source.disable_quantity_delivery,
        prepaid_returns=source.prepaid_returns,
        disable_sale_limit=source.disable_sale_limit,
    )


def convert_note(
    source: api_notes.IntegrationCustomerNote,
) -> application_operations.IntegrationCustomerNote:
    return application_operations.IntegrationCustomerNote(
        occurred_at=source.occurred_at,
        text=source.text,
        open=source.open,
    )


def convert_notes(
    source: api_notes.IntegrationCustomerNotes,
) -> application_operations.IntegrationCustomerNotes:
    return application_operations.IntegrationCustomerNotes(
        items=tuple(convert_note(note) for note in source.items),
        administrative_note=source.administrative_note,
    )


def convert_extensions(
    source: api_extensions.IntegrationCustomerExtensions,
) -> application_operations.IntegrationCustomerExtensions:
    return application_operations.IntegrationCustomerExtensions(
        parameters=source.parameters,
        extra_data=source.extra_data,
    )


def _convert_groups_patch(
    source: list[api_shop.IntegrationShopGroup] | UnsetType,
) -> tuple[application_operations.IntegrationShopGroup, ...] | UnsetType:
    if isinstance(source, UnsetType):
        return UNSET
    return tuple(convert_shop_group(group) for group in source)


def convert_shop_patch(
    source: api_patch.IntegrationShopPatch,
) -> application_patch.IntegrationShopPatch:
    return application_patch.IntegrationShopPatch(
        latitude=source.latitude,
        longitude=source.longitude,
        groups=_convert_groups_patch(source.groups),
    )


def convert_operational_settings_patch(
    source: api_patch.IntegrationOperationalSettingsPatch,
) -> application_patch.IntegrationOperationalSettingsPatch:
    return application_patch.IntegrationOperationalSettingsPatch(
        disable_box_discount=source.disable_box_discount,
        disable_quantity_delivery=source.disable_quantity_delivery,
        prepaid_returns=source.prepaid_returns,
        disable_sale_limit=source.disable_sale_limit,
    )


def _convert_notes_patch(
    source: list[api_notes.IntegrationCustomerNote] | UnsetType,
) -> tuple[application_operations.IntegrationCustomerNote, ...] | UnsetType:
    if isinstance(source, UnsetType):
        return UNSET
    return tuple(convert_note(note) for note in source)


def convert_customer_notes_patch(
    source: api_patch.IntegrationCustomerNotesPatch,
) -> application_patch.IntegrationCustomerNotesPatch:
    return application_patch.IntegrationCustomerNotesPatch(
        items=_convert_notes_patch(source.items),
        administrative_note=source.administrative_note,
    )


def convert_customer_extensions_patch(
    source: api_patch.IntegrationCustomerExtensionsPatch,
) -> application_patch.IntegrationCustomerExtensionsPatch:
    return application_patch.IntegrationCustomerExtensionsPatch(
        parameters=source.parameters,
        extra_data=source.extra_data,
    )
