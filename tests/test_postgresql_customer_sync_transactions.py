"""Transaction tests that require an empty, dedicated PostgreSQL test database."""

import asyncio
import json
import os
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import psycopg
import pytest
from psycopg import pq, sql
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import TupleRow

from app.api.integrations.converters.customer import convert_customer_data
from app.api.integrations.schemas.customer import (
    IntegrationCustomerData as CustomerRequestData,
)
from app.application.dtos.customer_integration.customer import IntegrationCustomerData
from app.application.dtos.customer_integration.customer_patch import CustomerUpdatedData
from app.application.dtos.customer_integration.events import (
    CustomerCreatedEvent,
    CustomerSynchronizationResult,
    CustomerUpdatedEvent,
)
from app.application.dtos.customer_integration.profile_patch import (
    IntegrationCompanyPatch,
)
from app.application.dtos.customer_integration.unset import UNSET
from app.application.exceptions import (
    CustomerNotFoundException,
    CustomerSynchronizationConflictException,
    StaleCustomerVersionException,
)
from app.application.ports import CustomerSynchronizationGateway
from app.application.services.customer_synchronization_service import (
    CustomerSynchronizationService,
)
from app.infrastructure.data_mapper.customer_sync.unit_of_work import (
    PostgreSQLCustomerSynchronizationUnitOfWork,
)

_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "migrations/0001_customer_synchronization.sql"
)
_CUSTOMER_FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures/integrations/salesforce/customer-created-v1.json"
)
_KEY = b"test-customer-sync-hmac-key-32-bytes"
_OCCURRED_AT = datetime(2026, 9, 25, 10, 0, tzinfo=UTC)
_DATABASE_PREFIX = "life365_public_api_test_"


class _TestCustomerGateway(CustomerSynchronizationGateway):
    def __init__(
        self, cur: psycopg.AsyncCursor[TupleRow], *, create_delay: float = 0
    ) -> None:
        self._cur = cur
        self._create_delay = create_delay

    async def customer_exists(self, reference_id: int) -> bool:
        await self._cur.execute(
            sql.SQL("SELECT 1 FROM public.customers WHERE id = %s"),
            (reference_id,),
        )
        return await self._cur.fetchone() is not None

    async def get_customer(
        self, reference_id: int
    ) -> IntegrationCustomerData | None:
        raise NotImplementedError("Full customer mapping belongs to Task 15")

    async def create_customer(self, data: IntegrationCustomerData) -> int:
        if self._create_delay:
            await asyncio.sleep(self._create_delay)
        await self._cur.execute(
            sql.SQL(
                "INSERT INTO public.customers (business_name) VALUES (%s) RETURNING id"
            ),
            (data.company.name,),
        )
        row = await self._cur.fetchone()
        assert row is not None
        return row[0]

    async def update_customer(
        self, reference_id: int, data: CustomerUpdatedData
    ) -> None:
        name = (
            data.company.name
            if isinstance(data.company, IntegrationCompanyPatch)
            and data.company.name is not UNSET
            else None
        )
        await self._cur.execute(
            sql.SQL(
                "UPDATE public.customers "
                "SET business_name = COALESCE(%s, business_name) WHERE id = %s"
            ),
            (name, reference_id),
        )
        if self._cur.rowcount == 0:
            raise CustomerNotFoundException(f"Customer {reference_id} does not exist")


def _test_database_url() -> str:
    url = os.environ.get("CUSTOMER_SYNC_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set CUSTOMER_SYNC_TEST_DATABASE_URL to an empty test database")

    database_name = conninfo_to_dict(url).get("dbname", "")
    if not database_name.startswith(_DATABASE_PREFIX):
        pytest.fail(
            f"Test database name must start with {_DATABASE_PREFIX}"
        )

    application_url = os.environ.get("DATABASE_URL")
    if application_url and conninfo_to_dict(application_url) == conninfo_to_dict(url):
        pytest.fail("The test database must differ from DATABASE_URL")
    return url


@pytest.fixture
def test_database_url() -> Iterator[str]:
    url = _test_database_url()
    with psycopg.connect(url, autocommit=True) as conn:
        actual_name = conn.execute(sql.SQL("SELECT current_database() ")).fetchone()
        assert actual_name is not None
        if not actual_name[0].startswith(_DATABASE_PREFIX):
            pytest.fail("The connected database is not a customer sync test database")

        existing = conn.execute(
            sql.SQL(
                "SELECT to_regclass('public.customers'), "
                "to_regclass('public.customer_synchronization_versions'), "
                "to_regclass('public.customer_synchronization_events')"
            )
        ).fetchone()
        if existing is None or any(table is not None for table in existing):
            pytest.fail("The customer sync test database must be empty")

        try:
            conn.execute(
                sql.SQL(
                    "CREATE TABLE public.customers ("
                    "id integer GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY, "
                    "business_name text NOT NULL)"
                )
            )
            conn.execute(_MIGRATION.read_text(encoding="utf-8"))
            yield url
        finally:
            if conn.info.transaction_status != pq.TransactionStatus.IDLE:
                conn.rollback()
            conn.execute(
                sql.SQL("DROP TABLE IF EXISTS public.customer_synchronization_events")
            )
            conn.execute(
                sql.SQL("DROP TABLE IF EXISTS public.customer_synchronization_versions")
            )
            conn.execute(sql.SQL("DROP TABLE IF EXISTS public.customers"))


def _customer_data() -> IntegrationCustomerData:
    payload = json.loads(_CUSTOMER_FIXTURE.read_text(encoding="utf-8"))["data"]
    return convert_customer_data(CustomerRequestData.model_validate(payload))


def _created_event(data: IntegrationCustomerData) -> CustomerCreatedEvent:
    return CustomerCreatedEvent(
        schema_version=1,
        event_id=UUID(int=1),
        occurred_at=_OCCURRED_AT,
        resource_version=1,
        data=data,
    )


def _unit_of_work(
    url: str, *, create_delay: float = 0
) -> PostgreSQLCustomerSynchronizationUnitOfWork:
    return PostgreSQLCustomerSynchronizationUnitOfWork(
        connection_string=url,
        fingerprint_secret=_KEY,
        customer_mapper_factory=lambda cur: _TestCustomerGateway(
            cur, create_delay=create_delay
        ),
    )


async def _row_counts(url: str) -> tuple[int, int, int]:
    async with await psycopg.AsyncConnection.connect(url) as conn:
        counts: list[int] = []
        for table in (
            "customers",
            "customer_synchronization_versions",
            "customer_synchronization_events",
        ):
            query = sql.SQL("SELECT count(*) FROM {}").format(
                sql.Identifier("public", table)
            )
            row = await (await conn.execute(query)).fetchone()
            assert row is not None
            counts.append(row[0])
    return counts[0], counts[1], counts[2]


@pytest.mark.anyio
async def test_rollback_discards_customer_version_and_event(
    test_database_url: str,
) -> None:
    event = _created_event(_customer_data())

    with pytest.raises(RuntimeError, match="stop transaction"):
        async with _unit_of_work(test_database_url) as work:
            reference_id = await work.customers.create_customer(event.data)
            await work.resource_versions.save_resource_version(reference_id, 1)
            await work.processed_events.save_processed_result(
                event, CustomerSynchronizationResult(True, reference_id)
            )
            await work.commit()
            raise RuntimeError("stop transaction")

    assert await _row_counts(test_database_url) == (0, 0, 0)


@pytest.mark.anyio
async def test_event_result_survives_a_new_unit_of_work(
    test_database_url: str,
) -> None:
    event = _created_event(_customer_data())
    first = await CustomerSynchronizationService(
        _unit_of_work(test_database_url)
    ).synchronize_customer(event)
    replay = await CustomerSynchronizationService(
        _unit_of_work(test_database_url)
    ).synchronize_customer(event)

    assert replay == first
    assert await _row_counts(test_database_url) == (1, 1, 1)

    changed_password = replace(
        event,
        data=replace(
            event.data,
            credentials=replace(event.data.credentials, password="different-password"),
        ),
    )
    with pytest.raises(CustomerSynchronizationConflictException):
        await CustomerSynchronizationService(
            _unit_of_work(test_database_url)
        ).synchronize_customer(changed_password)
    assert await _row_counts(test_database_url) == (1, 1, 1)

    async with await psycopg.AsyncConnection.connect(test_database_url) as conn:
        row = await (
            await conn.execute(
                sql.SQL(
                    "SELECT event_fingerprint "
                    "FROM public.customer_synchronization_events"
                )
            )
        ).fetchone()
        assert row is not None
        assert len(row[0]) == 32


@pytest.mark.anyio
async def test_simultaneous_duplicate_event_creates_one_customer(
    test_database_url: str,
) -> None:
    event = _created_event(_customer_data())

    async def deliver() -> CustomerSynchronizationResult:
        return await CustomerSynchronizationService(
            _unit_of_work(test_database_url, create_delay=0.1)
        ).synchronize_customer(event)

    first, second = await asyncio.gather(deliver(), deliver())

    assert first == second
    assert await _row_counts(test_database_url) == (1, 1, 1)


@pytest.mark.anyio
async def test_simultaneous_updates_accept_only_one_next_version(
    test_database_url: str,
) -> None:
    created = await CustomerSynchronizationService(
        _unit_of_work(test_database_url)
    ).synchronize_customer(_created_event(_customer_data()))

    async def deliver(event_number: int) -> object:
        event = CustomerUpdatedEvent(
            schema_version=1,
            event_id=UUID(int=event_number),
            occurred_at=_OCCURRED_AT,
            resource_version=2,
            reference_id=created.reference_id,
            data=CustomerUpdatedData(
                company=IntegrationCompanyPatch(name=f"Update {event_number}")
            ),
        )
        return await CustomerSynchronizationService(
            _unit_of_work(test_database_url)
        ).synchronize_customer(event)

    results = await asyncio.gather(deliver(2), deliver(3), return_exceptions=True)

    assert sum(
        isinstance(result, CustomerSynchronizationResult) for result in results
    ) == 1
    assert sum(
        isinstance(result, StaleCustomerVersionException) for result in results
    ) == 1
    assert await _row_counts(test_database_url) == (1, 1, 2)
