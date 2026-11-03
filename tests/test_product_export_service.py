"""Application tests use only the reader and Salesforce gateway ports."""

import logging
from dataclasses import replace

import pytest

from app.application.dtos.product_integration import (
    IntegrationProductData,
    ProductEventType,
    ProductExportEvent,
    ProductExportResult,
)
from app.application.exceptions import (
    DBException,
    InvalidProductReferenceException,
    ProductNotFoundException,
    SalesforceRequestException,
)
from app.application.services.product_export_service import ProductExportService
from app.infrastructure.data_mapper.product_export.product import product_from_row
from tests.test_product_export_mapping import product_row


def product_data() -> IntegrationProductData:
    return product_from_row(product_row())


class Reader:
    def __init__(self, data: IntegrationProductData | None) -> None:
        self.data = data
        self.calls: list[int] = []
        self.existence_calls: list[int] = []
        self.failure: Exception | None = None

    async def get_product(self, reference_id: int) -> IntegrationProductData | None:
        self.calls.append(reference_id)
        if self.failure is not None:
            raise self.failure
        return self.data

    async def product_exists(self, reference_id: int) -> bool:
        self.existence_calls.append(reference_id)
        if self.failure is not None:
            raise self.failure
        return self.data is not None


class Gateway:
    def __init__(self) -> None:
        self.events: list[ProductExportEvent] = []
        self.failure: Exception | None = None

    async def send_product(self, event: ProductExportEvent) -> ProductExportResult:
        self.events.append(event)
        if self.failure is not None:
            raise self.failure
        return ProductExportResult(True, event.event_id, event.reference_id, "01t-test")


@pytest.mark.anyio
@pytest.mark.parametrize("event_type", ["product.created", "product.updated"])
async def test_current_full_snapshot_and_new_event_per_call(
    event_type: ProductEventType, caplog: pytest.LogCaptureFixture
) -> None:
    reader, gateway = Reader(product_data()), Gateway()
    service = ProductExportService(reader, gateway)
    with caplog.at_level(logging.INFO):
        first = await service.export_product(101, event_type)
        assert reader.data is not None
        reader.data = replace(reader.data, name="Changed", active=False)
        second = await service.export_product(101, event_type)
    assert first.success and first.reference_id == second.reference_id == 101
    assert first.event_id != second.event_id
    assert reader.calls == [101, 101] and reader.existence_calls == []
    assert gateway.events[0].data == product_data()
    assert gateway.events[1].data == reader.data
    assert gateway.events[0].schema_version == 1
    assert gateway.events[0].occurred_at.utcoffset() is not None
    assert str(first.event_id) in caplog.text and "reference_id=101" in caplog.text


@pytest.mark.anyio
async def test_delete_only_checks_existence_and_sends_no_metadata() -> None:
    reader, gateway = Reader(product_data()), Gateway()
    result = await ProductExportService(reader, gateway).export_product(
        101, "product.deleted"
    )
    assert result.success and reader.calls == [] and reader.existence_calls == [101]
    assert gateway.events[0].data is None


@pytest.mark.anyio
@pytest.mark.parametrize(
    "kind", ["product.created", "product.updated", "product.deleted"]
)
async def test_missing_product_never_calls_salesforce(kind: ProductEventType) -> None:
    gateway = Gateway()
    with pytest.raises(ProductNotFoundException):
        await ProductExportService(Reader(None), gateway).export_product(101, kind)
    assert gateway.events == []


@pytest.mark.anyio
@pytest.mark.parametrize("reference", [0, -1, True])
async def test_invalid_reference_never_reads_or_sends(reference: int) -> None:
    reader, gateway = Reader(product_data()), Gateway()
    with pytest.raises(InvalidProductReferenceException):
        await ProductExportService(reader, gateway).export_product(
            reference, "product.created"
        )
    assert reader.calls == reader.existence_calls == gateway.events == []


@pytest.mark.anyio
async def test_failures_are_preserved_without_service_retries() -> None:
    reader, gateway = Reader(product_data()), Gateway()
    service = ProductExportService(reader, gateway)
    reader.failure = DBException("Unavailable")
    with pytest.raises(DBException):
        await service.export_product(101, "product.updated")
    assert gateway.events == []
    reader.failure = None
    gateway.failure = SalesforceRequestException("Remote unavailable")
    with pytest.raises(SalesforceRequestException):
        await service.export_product(101, "product.updated")
    assert len(gateway.events) == 1
