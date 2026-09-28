"""Resolve preferred category codes to Life365 category IDs."""

import psycopg
from psycopg import sql
from psycopg.rows import TupleRow

from app.application.dtos.customer_integration.commercial import IntegrationCategory
from app.application.exceptions import InvalidCustomerDataException

_CATEGORY_IDS_BY_CODE: dict[str, int] = {
    "cartridge-toner": 1,
    "smart-solutions": 2,
    "networking": 14,
    "myphone": 23,
    "solar-energy": 25,
    "lighting": 27,
    "electric-parts": 28,
    "special-business": 29,
    "power-tools": 30,
}

_SELECT_CATEGORY_IDS = sql.SQL(
    "SELECT id FROM public.categories WHERE id = ANY(%s)"
)


async def resolve_category_ids(
    cur: psycopg.AsyncCursor[TupleRow],
    categories: tuple[IntegrationCategory, ...],
) -> list[int]:
    """Keep input order and require every mapped category to exist."""
    category_ids: list[int] = []
    for category in categories:
        category_id = _CATEGORY_IDS_BY_CODE.get(category.code)
        if category_id is None:
            raise InvalidCustomerDataException(
                f"Unknown category code {category.code!r}"
            )
        category_ids.append(category_id)

    if not category_ids:
        return []

    await cur.execute(_SELECT_CATEGORY_IDS, (category_ids,))
    existing_ids = {row[0] for row in await cur.fetchall()}
    unavailable_codes = [
        category.code
        for category, category_id in zip(categories, category_ids, strict=True)
        if category_id not in existing_ids
    ]
    if unavailable_codes:
        raise InvalidCustomerDataException(
            f"Unavailable category codes: {', '.join(unavailable_codes)}"
        )
    return category_ids
