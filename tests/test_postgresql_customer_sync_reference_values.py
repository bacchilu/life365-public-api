"""Offline tests for customer create reference values."""

import json
from dataclasses import replace
from pathlib import Path
from typing import cast

import psycopg
import pytest
from psycopg import sql
from psycopg.rows import TupleRow

from app.api.integrations.converters.customer import convert_customer_data
from app.api.integrations.schemas.customer import (
    IntegrationCustomerData as CustomerRequestData,
)
from app.application.dtos.customer_integration.customer import IntegrationCustomerData
from app.application.exceptions import InvalidCustomerDataException
from app.infrastructure.data_mapper.customer_sync.reference_values import (
    resolve_customer_reference_values,
)

_FIXTURE_PATH = (
    Path(__file__).resolve().parent
    / "fixtures/integrations/salesforce/customer-created-v1.json"
)


def _customer_data() -> IntegrationCustomerData:
    payload = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))["data"]
    return convert_customer_data(CustomerRequestData.model_validate(payload))


class _FakeCursor:
    def __init__(self, *, missing_region: bool = False) -> None:
        self.missing_region = missing_region
        self.statements: list[tuple[str, tuple[object, ...]]] = []
        self._one: tuple[int | str] | None = None
        self._many: list[tuple[int]] = []

    async def execute(self, query: sql.SQL, params: tuple[object, ...]) -> None:
        statement = query.as_string()
        self.statements.append((statement, params))
        self._one = None
        self._many = []
        if "public.regions" in statement:
            self._one = None if self.missing_region else (158,)
        elif "public.agents" in statement:
            self._one = (117,)
        elif "public.categories" in statement:
            self._many = [(1,), (14,)]
        elif "public.sales_channels" in statement:
            self._one = (13,)
        elif "public.payment_types" in statement:
            self._one = ("BONIFICO",)
        elif "public.shop_groups" in statement:
            self._many = [(3,)]
        else:
            raise AssertionError(f"Unexpected lookup: {statement}")

    async def fetchone(self) -> tuple[int | str] | None:
        return self._one

    async def fetchall(self) -> list[tuple[int]]:
        return self._many


@pytest.mark.anyio
async def test_full_create_fixture_resolves_every_reference() -> None:
    cursor = _FakeCursor()

    values = await resolve_customer_reference_values(
        cast(psycopg.AsyncCursor[TupleRow], cursor), _customer_data()
    )

    assert values == {
        "region_id": 158,
        "delivery_region_id": 158,
        "agent_id": 117,
        "preferred_categories": [1, 14],
        "sales_channel_id": 13,
        "preferred_payment_type": "BONIFICO",
        "shop_group_ids": [3],
    }
    assert len(cursor.statements) == 7
    assert all(query.lstrip().startswith("SELECT") for query, _ in cursor.statements)


@pytest.mark.anyio
async def test_nullable_and_empty_references_keep_their_meaning() -> None:
    original = _customer_data()
    data = replace(
        original,
        delivery=replace(original.delivery, address=None),
        commercial=replace(
            original.commercial,
            assigned_agent=None,
            preferred_categories=(),
            preferred_payment_type_code=None,
        ),
        shop=replace(original.shop, groups=()),
    )
    cursor = _FakeCursor()

    values = await resolve_customer_reference_values(
        cast(psycopg.AsyncCursor[TupleRow], cursor), data
    )

    assert values == {
        "region_id": 158,
        "delivery_region_id": None,
        "agent_id": 1,
        "preferred_categories": [],
        "sales_channel_id": 13,
        "preferred_payment_type": None,
        "shop_group_ids": [],
    }
    assert len(cursor.statements) == 2


@pytest.mark.anyio
async def test_null_sales_channel_is_stored_as_sql_null() -> None:
    original = _customer_data()
    data = replace(
        original,
        commercial=replace(original.commercial, sales_channel=None),
    )
    cursor = _FakeCursor()

    values = await resolve_customer_reference_values(
        cast(psycopg.AsyncCursor[TupleRow], cursor), data
    )

    assert values["sales_channel_id"] is None
    assert all("public.sales_channels" not in query for query, _ in cursor.statements)


@pytest.mark.anyio
async def test_unknown_region_stops_reference_resolution() -> None:
    cursor = _FakeCursor(missing_region=True)

    with pytest.raises(InvalidCustomerDataException, match="Unknown region"):
        await resolve_customer_reference_values(
            cast(psycopg.AsyncCursor[TupleRow], cursor), _customer_data()
        )

    assert len(cursor.statements) == 1
