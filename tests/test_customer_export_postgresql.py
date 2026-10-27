"""Read/export the bundled seed exclusively in the dedicated PostgreSQL test DB."""

import asyncio
import json
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import httpx
import psycopg
import pytest
from psycopg import sql
from psycopg.types.json import Jsonb

import app.api.integrations.export_dependencies as composition
from app.api.integrations.converters.events import convert_customer_event
from app.api.integrations.schemas.events import CustomerCreatedEventRequest
from app.application.dtos.customer_integration.export import CustomerExportEvent
from app.application.dtos.customer_integration.operations import IntegrationCustomerNote
from app.application.exceptions import InvalidCustomerDataException
from app.application.services.customer_synchronization_service import (
    CustomerSynchronizationService,
)
from app.infrastructure.data_mapper.customer_export import (
    PostgreSQLCustomerExportDataMapper,
)
from app.infrastructure.data_mapper.customer_sync.customers import (
    PostgreSQLCustomerDataMapper,
)
from app.infrastructure.data_mapper.customer_sync.unit_of_work import (
    PostgreSQLCustomerSynchronizationUnitOfWork,
)
from app.infrastructure.salesforce import (
    SalesforceCustomerAPI,
    SalesforceSettings,
    auth,
)
from app.infrastructure.salesforce.payload import customer_event_payload
from tests.test_customer_export_service import customer_data
from tests.test_sandbox_postgresql import _app, _client, _headers, _state
from tests.test_sandbox_postgresql import database_url as seeded_database_fixture

database_url = seeded_database_fixture


@pytest.mark.anyio
async def test_seeded_customer_full_read_and_no_local_writes(database_url: str) -> None:
    before = _state(database_url)
    reader = PostgreSQLCustomerExportDataMapper(database_url)
    data = await reader.get_customer(1)
    assert data is not None
    assert data.credentials.login == "sandbox-customer-1"
    assert data.credentials.password == "sandbox-customer"
    assert data.company.name == "Sample Business 1"
    assert data.primary_contact.additional_emails[0].commercial is True
    assert data.billing_address.country_code == "IT"
    assert data.billing_address.region_name
    assert data.registration.registered_at == datetime(2026, 1, 10, 12, tzinfo=UTC)
    assert data.commercial.preferred_categories[0].code == "cartridge-toner"
    assert data.commercial.preferred_categories[0].label == "Cartridge&Toner"
    assert data.commercial.sales_channel is not None
    assert data.commercial.sales_channel.code == "N7"
    assert data.commercial.assigned_agent is not None
    assert data.commercial.assigned_agent.name == "Sample Agent 1"
    assert data.extensions.parameters == {"sandbox": True, "nested": {"keep": 1}}
    assert await reader.get_customer(999999) is None
    assert _state(database_url) == before


@pytest.mark.anyio
async def test_round_trip_covers_complete_dto_and_exact_values(
    database_url: str,
) -> None:
    original = customer_data()
    original = replace(
        original,
        notes=replace(
            original.notes,
            items=(
                IntegrationCustomerNote(
                    datetime(2026, 10, 27, 10, tzinfo=UTC), "Test note", False
                ),
            ),
        ),
        commercial=replace(original.commercial, credit_value=Decimal("12345678.99")),
    )
    incoming_payload = customer_event_payload(
        CustomerExportEvent(
            event_id=uuid4(),
            occurred_at=datetime.now(UTC),
            event_type="customer.created",
            reference_id=1,
            data=original,
        )
    )
    del incoming_payload["referenceId"]
    incoming = convert_customer_event(
        CustomerCreatedEventRequest.model_validate(incoming_payload)
    )
    work = PostgreSQLCustomerSynchronizationUnitOfWork(
        database_url,
        b"test-customer-sync-key-at-least-32-bytes",
        lambda cursor: PostgreSQLCustomerDataMapper(
            cursor, registration_ip="127.0.0.1"
        ),
    )
    result = await CustomerSynchronizationService(work).synchronize_customer(incoming)
    exported = await PostgreSQLCustomerExportDataMapper(database_url).get_customer(
        result.reference_id
    )
    assert exported is not None and exported.commercial.assigned_agent is not None
    assert exported.commercial.sales_channel is not None
    expected = replace(
        original,
        commercial=replace(
            original.commercial,
            assigned_agent=exported.commercial.assigned_agent,
            sales_channel=replace(
                original.commercial.sales_channel,
                label=exported.commercial.sales_channel.label,
            )
            if original.commercial.sales_channel
            else None,
        ),
    )
    assert exported == expected


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("business_name", None),
        ("region_id", None),
        ("preferred_categories", [50]),
        ("additional_emails", Jsonb([{"email": "missing-flags@example.com"}])),
        ("parameters", Jsonb([])),
    ],
)
async def test_unrepresentable_legacy_values_fail_explicitly(
    database_url: str, column: str, value: object
) -> None:
    with psycopg.connect(database_url) as connection:
        connection.execute(
            sql.SQL("UPDATE public.customers SET {} = %s WHERE id = 1").format(
                sql.Identifier(column)
            ),
            (value,),
        )
    with pytest.raises(InvalidCustomerDataException):
        await PostgreSQLCustomerExportDataMapper(database_url).get_customer(1)


@pytest.mark.anyio
async def test_authenticated_sandbox_post_put_use_real_adapter_with_mock_http(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(auth, "_access_token", None)
    monkeypatch.setattr(auth, "_credentials_key", None)
    monkeypatch.setattr(auth, "_token_lock", asyncio.Lock())
    payloads: list[dict[str, object]] = []
    authentications = 0

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal authentications
        if request.url.path.endswith("/token"):
            authentications += 1
            return httpx.Response(200, json={"access_token": "test-token"})
        assert request.method == "POST"
        payload = json.loads(request.content)
        payloads.append(payload)
        return httpx.Response(
            201,
            json={
                "success": True,
                "eventId": payload["eventId"],
                "referenceId": str(payload["referenceId"]),
                "accountId": "001-test",
            },
        )

    settings = SalesforceSettings(
        "https://unit.my.salesforce.com/services/oauth2/token",
        "https://unit.my.salesforce.com/services/apexrest/customer/sync/",
        "test-id",
        "test-secret",
    )
    before = _state(database_url)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as remote:
        monkeypatch.setattr(
            composition, "_salesforce_gateway", SalesforceCustomerAPI(settings, remote)
        )
        async with _client(_app(database_url)) as client:
            headers = await _headers(client)
            url = "/sandbox/integrations/salesforce/customers/1"
            created = await client.post(url, headers=headers)
            updated = await client.put(url, headers=headers)
            missing = await client.put(url.replace("/1", "/999999"), headers=headers)
    assert created.status_code == 201, created.text
    assert updated.status_code == 200, updated.text
    assert missing.status_code == 404
    assert authentications == 1 and len(payloads) == 2
    assert [payload["eventType"] for payload in payloads] == [
        "customer.created",
        "customer.updated",
    ]
    assert payloads[0]["referenceId"] == payloads[1]["referenceId"] == 1
    assert payloads[0]["data"] == payloads[1]["data"]
    assert _state(database_url) == before
