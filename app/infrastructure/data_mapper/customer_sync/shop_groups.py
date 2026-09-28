"""Resolve integration shop-group codes to Life365 IDs."""

import psycopg
from psycopg import sql
from psycopg.rows import TupleRow

from app.application.dtos.customer_integration.operations import IntegrationShopGroup
from app.application.exceptions import InvalidCustomerDataException

_SHOP_GROUP_IDS_BY_CODE: dict[str, int] = {
    "rei-la-rete": 1,
    "geser-prodigix": 2,
    "professional-group": 3,
    "closed-activity": 36,
}

_SELECT_SHOP_GROUP_IDS = sql.SQL(
    "SELECT id FROM public.shop_groups WHERE id = ANY(%s)"
)


async def resolve_shop_group_ids(
    cur: psycopg.AsyncCursor[TupleRow],
    groups: tuple[IntegrationShopGroup, ...],
) -> list[int]:
    """Keep input order and require every mapped shop group to exist."""
    group_ids: list[int] = []
    for group in groups:
        group_id = _SHOP_GROUP_IDS_BY_CODE.get(group.code)
        if group_id is None:
            raise InvalidCustomerDataException(
                f"Unknown shop-group code {group.code!r}"
            )
        group_ids.append(group_id)

    if not group_ids:
        return []

    await cur.execute(_SELECT_SHOP_GROUP_IDS, (group_ids,))
    existing_ids = {row[0] for row in await cur.fetchall()}
    unavailable_codes = [
        group.code
        for group, group_id in zip(groups, group_ids, strict=True)
        if group_id not in existing_ids
    ]
    if unavailable_codes:
        raise InvalidCustomerDataException(
            f"Unavailable shop-group codes: {', '.join(unavailable_codes)}"
        )
    return group_ids
