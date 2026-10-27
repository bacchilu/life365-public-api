"""Pure use-case tests: no database, HTTP, event tables, or retry state."""

import json
import logging
from dataclasses import replace
from pathlib import Path

import pytest

from app.api.integrations.converters.customer import convert_customer_data
from app.api.integrations.schemas.customer import (
    IntegrationCustomerData as CustomerRequest,
)
from app.application.dtos.customer_integration.customer import IntegrationCustomerData
from app.application.dtos.customer_integration.events import CustomerEventType
from app.application.dtos.customer_integration.export import (
    CustomerExportEvent,
    CustomerExportResult,
)
from app.application.exceptions import (
    CustomerNotFoundException,
    DBException,
    InvalidCustomerReferenceException,
    SalesforceRequestException,
)
from app.application.services.customer_export_service import CustomerExportService


def customer_data() -> IntegrationCustomerData:
    path = (
        Path(__file__).parent
        / "fixtures/integrations/salesforce/customer-created-v1.json"
    )
    return convert_customer_data(
        CustomerRequest.model_validate(
            json.loads(path.read_text(encoding="utf-8"))["data"]
        )
    )


class Reader:
    def __init__(self, customer: IntegrationCustomerData | None) -> None:
        self.customer = customer
        self.calls: list[int] = []
        self.failure: Exception | None = None

    async def get_customer(self, reference_id: int) -> IntegrationCustomerData | None:
        self.calls.append(reference_id)
        if self.failure is not None:
            raise self.failure
        return self.customer


class Gateway:
    def __init__(self) -> None:
        self.events: list[CustomerExportEvent] = []
        self.failure: Exception | None = None

    async def send_customer(self, event: CustomerExportEvent) -> CustomerExportResult:
        self.events.append(event)
        if self.failure is not None:
            raise self.failure
        return CustomerExportResult(
            True, event.event_id, event.reference_id, "001-test"
        )


@pytest.mark.anyio
@pytest.mark.parametrize("event_type", ["customer.created", "customer.updated"])
async def test_export_reads_complete_current_data_and_does_not_persist(
    event_type: CustomerEventType, caplog: pytest.LogCaptureFixture
) -> None:
    data = customer_data()
    reader, gateway = Reader(data), Gateway()
    service = CustomerExportService(reader, gateway)
    with caplog.at_level(logging.INFO):
        first = await service.export_customer(42, event_type)
        reader.customer = replace(data, company=replace(data.company, website=None))
        second = await service.export_customer(42, event_type)
    assert first.success is True and first.reference_id == 42
    assert first.event_id != second.event_id
    assert reader.calls == [42, 42] and len(gateway.events) == 2
    assert gateway.events[0].data is data
    assert gateway.events[1].data.company.website is None
    assert gateway.events[0].event_type == event_type
    assert gateway.events[0].schema_version == 1
    assert gateway.events[0].occurred_at.utcoffset() is not None
    assert data.credentials.password not in repr(gateway.events[0])
    assert data.credentials.password not in caplog.text
    assert str(first.event_id) in caplog.text and "reference_id=42" in caplog.text


@pytest.mark.anyio
async def test_missing_customer_does_not_call_salesforce() -> None:
    gateway = Gateway()
    with pytest.raises(CustomerNotFoundException):
        await CustomerExportService(Reader(None), gateway).export_customer(
            42, "customer.created"
        )
    assert gateway.events == []


@pytest.mark.anyio
@pytest.mark.parametrize("reference_id", [0, -1, True])
async def test_invalid_reference_never_reads_or_sends(reference_id: int) -> None:
    reader, gateway = Reader(customer_data()), Gateway()
    with pytest.raises(InvalidCustomerReferenceException):
        await CustomerExportService(reader, gateway).export_customer(
            reference_id, "customer.updated"
        )
    assert reader.calls == [] and gateway.events == []


@pytest.mark.anyio
async def test_errors_are_preserved_without_service_retries() -> None:
    reader, gateway = Reader(customer_data()), Gateway()
    reader.failure = DBException("DB unavailable")
    with pytest.raises(DBException):
        await CustomerExportService(reader, gateway).export_customer(
            42, "customer.updated"
        )
    assert gateway.events == []
    reader.failure = None
    gateway.failure = SalesforceRequestException("Remote unavailable")
    with pytest.raises(SalesforceRequestException):
        await CustomerExportService(reader, gateway).export_customer(
            42, "customer.updated"
        )
    assert len(gateway.events) == 1
