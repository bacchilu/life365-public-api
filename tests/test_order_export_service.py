"""The service knows only typed events and the two application ports."""

import logging
from dataclasses import replace

import pytest

from app.application.dtos.order_integration import (
    IntegrationOrderData,
    OrderEventType,
    OrderExportEvent,
    OrderExportResult,
)
from app.application.exceptions import (
    DBException,
    InvalidOrderReferenceException,
    OrderNotFoundException,
    SalesforceRequestException,
)
from app.application.services.order_export_service import OrderExportService
from app.infrastructure.data_mapper.order_export.order import order_from_rows
from tests.test_order_export_mapping import order_details, order_row, shipping_products


def order_data() -> IntegrationOrderData:
    return order_from_rows(order_row(), order_details(), shipping_products())


class Reader:
    def __init__(self, data: IntegrationOrderData | None) -> None:
        self.data = data
        self.calls: list[int] = []
        self.existence_calls: list[int] = []
        self.failure: Exception | None = None

    async def get_order(self, reference_id: int) -> IntegrationOrderData | None:
        self.calls.append(reference_id)
        if self.failure is not None:
            raise self.failure
        return self.data

    async def order_exists(self, reference_id: int) -> bool:
        self.existence_calls.append(reference_id)
        if self.failure is not None:
            raise self.failure
        return self.data is not None


class Gateway:
    def __init__(self) -> None:
        self.events: list[OrderExportEvent] = []
        self.failure: Exception | None = None

    async def send_order(self, event: OrderExportEvent) -> OrderExportResult:
        self.events.append(event)
        if self.failure is not None:
            raise self.failure
        return OrderExportResult(True, event.event_id, event.reference_id, "801-test")


@pytest.mark.anyio
@pytest.mark.parametrize("kind", ["order.created", "order.updated"])
async def test_current_snapshot_new_event_and_safe_logs(
    kind: OrderEventType, caplog: pytest.LogCaptureFixture
) -> None:
    reader, gateway = Reader(order_data()), Gateway()
    service = OrderExportService(reader, gateway)
    with caplog.at_level(logging.INFO):
        first = await service.export_order(1001, kind)
        reader.data = replace(order_data(), status="DELIVERED")
        second = await service.export_order(1001, kind)
    assert first.success and first.reference_id == second.reference_id == 1001
    assert first.event_id != second.event_id
    assert reader.calls == [1001, 1001] and reader.existence_calls == []
    assert (
        gateway.events[0].data == order_data() and gateway.events[1].data == reader.data
    )
    assert gateway.events[0].occurred_at.utcoffset() is not None
    assert str(first.event_id) in caplog.text and "reference_id=1001" in caplog.text
    assert "Deliver in the morning" not in caplog.text


@pytest.mark.anyio
async def test_delete_only_checks_existence_and_omits_data() -> None:
    reader, gateway = Reader(order_data()), Gateway()
    assert (
        await OrderExportService(reader, gateway).export_order(1001, "order.deleted")
    ).success
    assert reader.calls == [] and reader.existence_calls == [1001]
    assert gateway.events[0].data is None


@pytest.mark.anyio
@pytest.mark.parametrize("kind", ["order.created", "order.updated", "order.deleted"])
async def test_missing_order_does_not_send(kind: OrderEventType) -> None:
    gateway = Gateway()
    with pytest.raises(OrderNotFoundException):
        await OrderExportService(Reader(None), gateway).export_order(1001, kind)
    assert gateway.events == []


@pytest.mark.anyio
@pytest.mark.parametrize("identifier", [0, -1, True])
async def test_invalid_id_does_not_read_or_send(identifier: int) -> None:
    reader, gateway = Reader(order_data()), Gateway()
    with pytest.raises(InvalidOrderReferenceException):
        await OrderExportService(reader, gateway).export_order(
            identifier, "order.created"
        )
    assert reader.calls == reader.existence_calls == gateway.events == []


@pytest.mark.anyio
async def test_failures_are_preserved_and_no_service_retries() -> None:
    reader, gateway = Reader(order_data()), Gateway()
    service = OrderExportService(reader, gateway)
    reader.failure = DBException("Unavailable")
    with pytest.raises(DBException):
        await service.export_order(1001, "order.updated")
    assert gateway.events == []
    reader.failure = None
    gateway.failure = SalesforceRequestException("Unavailable")
    with pytest.raises(SalesforceRequestException):
        await service.export_order(1001, "order.updated")
    assert len(gateway.events) == 1


@pytest.mark.anyio
async def test_service_rejects_inconsistent_gateway_result() -> None:
    class WrongGateway(Gateway):
        async def send_order(self, event: OrderExportEvent) -> OrderExportResult:
            return OrderExportResult(True, event.event_id, 999, "801-test")

    with pytest.raises(SalesforceRequestException):
        await OrderExportService(Reader(order_data()), WrongGateway()).export_order(
            1001, "order.created"
        )
