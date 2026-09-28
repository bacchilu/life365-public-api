"""Resolve only the references supplied by a customer update."""

from collections.abc import Mapping
from typing import Any

import psycopg
from psycopg.rows import TupleRow

from app.application.dtos.customer_integration.address_patch import (
    IntegrationAddressPatch,
)
from app.application.dtos.customer_integration.customer_patch import CustomerUpdatedData
from app.application.dtos.customer_integration.unset import UNSET
from app.application.exceptions import CustomerSynchronizationConflictException

from .agents import resolve_agent_id
from .categories import resolve_category_ids
from .logins import reserve_customer_login
from .payment_types import resolve_payment_type_code
from .regions import resolve_region_name
from .sales_channels import resolve_sales_channel_code
from .shop_groups import resolve_shop_group_ids


async def _patched_region_id(
    cur: psycopg.AsyncCursor[TupleRow],
    patch: IntegrationAddressPatch,
    country_code: str | None,
    region_name: str | None,
) -> int | None:
    if patch.country_code is UNSET and patch.region_name is UNSET:
        return None
    country = country_code if patch.country_code is UNSET else patch.country_code
    region = region_name if patch.region_name is UNSET else patch.region_name
    if country is None or region is None:
        raise CustomerSynchronizationConflictException(
            "Address region patch needs both countryCode and regionName"
        )
    return await resolve_region_name(cur, country, region)


async def customer_reference_update_values(
    cur: psycopg.AsyncCursor[TupleRow],
    reference_id: int,
    data: CustomerUpdatedData,
    current: Mapping[str, Any],
) -> dict[str, object]:
    values: dict[str, object] = {}
    if data.credentials is not UNSET and data.credentials.login is not UNSET:
        values["login"] = await reserve_customer_login(
            cur, data.credentials.login, current_id=reference_id
        )

    if data.billing_address is not UNSET:
        region_id = await _patched_region_id(
            cur,
            data.billing_address,
            current["billing_country_code"],
            current["billing_region_name"],
        )
        if region_id is not None:
            values["region_id"] = region_id

    if data.delivery is not UNSET:
        address = data.delivery.address
        if address is None:
            values.update(
                delivery_address=None,
                delivery_city=None,
                delivery_zip_code=None,
                delivery_region_id=None,
            )
        elif address is not UNSET:
            if current["delivery_address"] is None:
                if any(
                    getattr(address, name) is UNSET
                    for name in (
                        "street", "city", "postal_code", "country_code", "region_name"
                    )
                ):
                    raise CustomerSynchronizationConflictException(
                        "A new delivery address needs every address field"
                    )
            for field_name, column in (
                ("street", "delivery_address"),
                ("city", "delivery_city"),
                ("postal_code", "delivery_zip_code"),
            ):
                field_value = getattr(address, field_name)
                if field_value is not UNSET:
                    values[column] = field_value
            region_id = await _patched_region_id(
                cur,
                address,
                current["delivery_country_code"],
                current["delivery_region_name"],
            )
            if region_id is not None:
                values["delivery_region_id"] = region_id

    if data.commercial is not UNSET:
        commercial = data.commercial
        if commercial.preferred_categories is not UNSET:
            values["preferred_categories"] = await resolve_category_ids(
                cur, commercial.preferred_categories
            )
        if commercial.assigned_agent is not UNSET:
            values["agent_id"] = await resolve_agent_id(
                cur, commercial.assigned_agent
            )
        if commercial.sales_channel is None:
            values["sales_channel_id"] = None
        elif commercial.sales_channel is not UNSET:
            channel = commercial.sales_channel
            if current["sales_channel_id"] is None and (
                channel.code is UNSET or channel.label is UNSET
            ):
                raise CustomerSynchronizationConflictException(
                    "A new sales channel needs its code and label"
                )
            if channel.code is not UNSET:
                values["sales_channel_id"] = await resolve_sales_channel_code(
                    cur, channel.code
                )
        payment_type = commercial.preferred_payment_type_code
        if payment_type is not UNSET:
            values["preferred_payment_type"] = (
                await resolve_payment_type_code(cur, payment_type)
                if payment_type is not None
                else None
            )

    if data.shop is not UNSET and data.shop.groups is not UNSET:
        values["shop_group_ids"] = await resolve_shop_group_ids(cur, data.shop.groups)
    return values
