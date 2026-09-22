"""Convert API address schemas to application DTOs."""

from app.api.integrations.schemas import address as api_address
from app.api.integrations.schemas import address_patch as api_patch
from app.application.dtos.customer_integration import address as application_address
from app.application.dtos.customer_integration import (
    address_patch as application_patch,
)
from app.application.dtos.customer_integration.unset import UNSET, UnsetType


def convert_address(
    source: api_address.IntegrationAddress,
) -> application_address.IntegrationAddress:
    return application_address.IntegrationAddress(
        street=source.street,
        city=source.city,
        postal_code=source.postal_code,
        country_code=source.country_code,
        region_name=source.region_name,
    )


def convert_delivery(
    source: api_address.IntegrationDelivery,
) -> application_address.IntegrationDelivery:
    address = convert_address(source.address) if source.address is not None else None
    return application_address.IntegrationDelivery(
        business_name=source.business_name,
        contact_name=source.contact_name,
        phone=source.phone,
        address=address,
    )


def convert_address_patch(
    source: api_patch.IntegrationAddressPatch,
) -> application_patch.IntegrationAddressPatch:
    return application_patch.IntegrationAddressPatch(
        street=source.street,
        city=source.city,
        postal_code=source.postal_code,
        country_code=source.country_code,
        region_name=source.region_name,
    )


def convert_delivery_patch(
    source: api_patch.IntegrationDeliveryPatch,
) -> application_patch.IntegrationDeliveryPatch:
    address: application_patch.IntegrationAddressPatch | None | UnsetType
    if isinstance(source.address, UnsetType):
        address = UNSET
    elif source.address is None:
        address = None
    else:
        address = convert_address_patch(source.address)

    return application_patch.IntegrationDeliveryPatch(
        business_name=source.business_name,
        contact_name=source.contact_name,
        phone=source.phone,
        address=address,
    )
