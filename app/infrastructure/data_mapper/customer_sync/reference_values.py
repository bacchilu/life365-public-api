"""Resolve customer integration references before a PostgreSQL insert."""

import psycopg
from psycopg.rows import TupleRow

from app.application.dtos.customer_integration.customer import IntegrationCustomerData

from .agents import resolve_agent_id
from .categories import resolve_category_ids
from .payment_types import resolve_payment_type_code
from .regions import resolve_region_id
from .sales_channels import resolve_sales_channel_id
from .shop_groups import resolve_shop_group_ids


async def resolve_customer_reference_values(
    cur: psycopg.AsyncCursor[TupleRow], data: IntegrationCustomerData
) -> dict[str, object]:
    """Resolve every reference with the active customer-write cursor."""
    channel = data.commercial.sales_channel
    delivery_address = data.delivery.address
    return {
        "region_id": await resolve_region_id(cur, data.billing_address),
        "delivery_region_id": (
            await resolve_region_id(cur, delivery_address)
            if delivery_address is not None
            else None
        ),
        "agent_id": await resolve_agent_id(cur, data.commercial.assigned_agent),
        "preferred_categories": await resolve_category_ids(
            cur, data.commercial.preferred_categories
        ),
        "sales_channel_id": (
            await resolve_sales_channel_id(cur, channel) if channel is not None else None
        ),
        "preferred_payment_type": (
            await resolve_payment_type_code(
                cur, data.commercial.preferred_payment_type_code
            )
            if data.commercial.preferred_payment_type_code is not None
            else None
        ),
        "shop_group_ids": await resolve_shop_group_ids(cur, data.shop.groups),
    }
