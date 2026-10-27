"""Resolve local foreign keys to the shared export reference objects."""

from collections.abc import Mapping
from typing import Any

from app.application.dtos.customer_integration.address import IntegrationAddress
from app.application.dtos.customer_integration.commercial import (
    IntegrationAgent,
    IntegrationCategory,
    IntegrationSalesChannel,
)
from app.application.dtos.customer_integration.operations import IntegrationShopGroup
from app.application.exceptions import InvalidCustomerDataException
from app.infrastructure.data_mapper.customer_sync.reference_codes import (
    CATEGORY_IDS_BY_CODE,
    SALES_CHANNEL_IDS_BY_CODE,
    SHOP_GROUP_IDS_BY_CODE,
    code_for_id,
)

from .values import objects, required_string


def address(row: Mapping[str, Any], *, delivery: bool = False) -> IntegrationAddress:
    street = "delivery_address" if delivery else "address_street"
    city = "delivery_city" if delivery else "address_city"
    postal_code = "delivery_zip_code" if delivery else "address_zip_code"
    prefix = "delivery" if delivery else "billing"
    return IntegrationAddress(
        street=required_string(row[street], f"{prefix}Address.street"),
        city=required_string(row[city], f"{prefix}Address.city"),
        postal_code=row[postal_code],
        country_code=required_string(
            row[f"{prefix}_country_code"], f"{prefix}Address.countryCode"
        ),
        region_name=required_string(
            row[f"{prefix}_region_name"], f"{prefix}Address.regionName"
        ),
    )


def agent(row: Mapping[str, Any]) -> IntegrationAgent | None:
    if row["agent_id"] is None:
        return None
    return IntegrationAgent(
        reference_id=row["agent_id"],
        user_login=required_string(row["agent_login"], "assignedAgent.userLogin"),
        name=required_string(row["agent_name"], "assignedAgent.name"),
        email=required_string(row["agent_email"], "assignedAgent.email"),
        phone=row["agent_phone"],
    )


def sales_channel(row: Mapping[str, Any]) -> IntegrationSalesChannel | None:
    if row["sales_channel_id"] is None:
        return None
    code = code_for_id(
        SALES_CHANNEL_IDS_BY_CODE, row["sales_channel_id"], "salesChannel"
    )
    label = required_string(row["channel_name"], "salesChannel.label")
    prefix, separator, rest = label.partition(" ")
    if prefix == code and separator:
        label = rest.strip()
    return IntegrationSalesChannel(code=code, label=label)


def categories(value: object) -> tuple[IntegrationCategory, ...]:
    result: list[IntegrationCategory] = []
    for item in objects(value, "preferredCategories"):
        local_id = item.get("id")
        if type(local_id) is not int:
            raise InvalidCustomerDataException(
                "Customer export has an invalid category reference"
            )
        code = code_for_id(CATEGORY_IDS_BY_CODE, local_id, "preferredCategories")
        names = item.get("name")
        if not isinstance(names, dict):
            raise InvalidCustomerDataException(
                "Customer export category has no translated name"
            )
        label = names.get("en") or names.get("it")
        result.append(
            IntegrationCategory(
                code, required_string(label, "preferredCategories.label")
            )
        )
    return tuple(result)


def groups(value: object) -> tuple[IntegrationShopGroup, ...]:
    result: list[IntegrationShopGroup] = []
    for item in objects(value, "shop.groups"):
        local_id = item.get("id")
        if type(local_id) is not int:
            raise InvalidCustomerDataException(
                "Customer export has an invalid shop-group reference"
            )
        code = code_for_id(SHOP_GROUP_IDS_BY_CODE, local_id, "shop.groups")
        result.append(
            IntegrationShopGroup(
                code, required_string(item.get("name"), "shop.groups.label")
            )
        )
    return tuple(result)
