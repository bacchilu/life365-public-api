"""Apply a partial customer update inside one PostgreSQL transaction."""

import psycopg
from psycopg import sql
from psycopg.rows import TupleRow

from app.application.dtos.customer_integration.customer_patch import CustomerUpdatedData
from app.application.exceptions import (
    CustomerNotFoundException,
    InvalidCustomerDataException,
)

from .update_json import customer_json_update_values
from .update_references import customer_reference_update_values
from .update_values import customer_direct_update_values

_CURRENT_COLUMNS = (
    "fiscal_code",
    "vat_number",
    "parameters",
    "extra_data",
    "sales_channel_id",
    "delivery_address",
    "billing_region_name",
    "billing_country_code",
    "delivery_region_name",
    "delivery_country_code",
)
_LOCK_CUSTOMER = sql.SQL(
    """
    SELECT c.fiscal_code, c.vat_number, c.parameters, c.extra_data,
           c.sales_channel_id, c.delivery_address,
           br.region_name, bc.iso_alpha_2,
           dr.region_name, dc.iso_alpha_2
    FROM public.customers AS c
    LEFT JOIN public.regions AS br ON br.id = c.region_id
    LEFT JOIN public.countries AS bc ON bc.id = br.country_id
    LEFT JOIN public.regions AS dr ON dr.id = c.delivery_region_id
    LEFT JOIN public.countries AS dc ON dc.id = dr.country_id
    WHERE c.id = %s
    FOR UPDATE OF c
    """
)


async def update_customer_row(
    cur: psycopg.AsyncCursor[TupleRow], reference_id: int, data: CustomerUpdatedData
) -> None:
    await cur.execute(_LOCK_CUSTOMER, (reference_id,))
    row = await cur.fetchone()
    if row is None:
        raise CustomerNotFoundException(f"Customer {reference_id} does not exist")
    current = dict(zip(_CURRENT_COLUMNS, row, strict=True))

    values = customer_direct_update_values(data)
    values.update(
        await customer_reference_update_values(cur, reference_id, data, current)
    )
    values.update(customer_json_update_values(data, current))

    fiscal_code = values.get("fiscal_code", current["fiscal_code"])
    vat_number = values.get("vat_number", current["vat_number"])
    if not (isinstance(fiscal_code, str) and fiscal_code.strip()) and not (
        isinstance(vat_number, str) and vat_number.strip()
    ):
        raise InvalidCustomerDataException("Customer needs a fiscal code or VAT number")

    if not values:
        return

    query = sql.SQL(
        "UPDATE public.customers SET {assignments} "
        "WHERE id = %(reference_id)s RETURNING id"
    ).format(
        assignments=sql.SQL(", ").join(
            sql.SQL("{} = {}").format(sql.Identifier(column), sql.Placeholder(column))
            for column in values
        )
    )
    await cur.execute(query, {**values, "reference_id": reference_id})
    if await cur.fetchone() is None:
        raise CustomerNotFoundException(f"Customer {reference_id} does not exist")
