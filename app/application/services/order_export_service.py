"""Read the selected order and send one event without local mutations."""

import logging
from datetime import UTC, datetime
from uuid import uuid4

from app.application.dtos.order_integration import (
    OrderEventType,
    OrderExportEvent,
    OrderExportResult,
)
from app.application.exceptions import (
    InvalidOrderReferenceException,
    OrderNotFoundException,
    SalesforceRequestException,
)
from app.application.ports import OrderExportReader, SalesforceOrderGateway

logger = logging.getLogger(__name__)


class OrderExportService:
    def __init__(
        self, reader: OrderExportReader, salesforce_gateway: SalesforceOrderGateway
    ) -> None:
        self._reader = reader
        self._salesforce_gateway = salesforce_gateway

    async def export_order(
        self, reference_id: int, event_type: OrderEventType
    ) -> OrderExportResult:
        if type(reference_id) is not int or reference_id <= 0:
            raise InvalidOrderReferenceException("Order reference must be positive")
        if event_type not in ("order.created", "order.updated", "order.deleted"):
            raise ValueError("Unsupported order export event type")
        data = None
        if event_type == "order.deleted":
            exists = await self._reader.order_exists(reference_id)
        else:
            data = await self._reader.get_order(reference_id)
            exists = data is not None
        if not exists:
            raise OrderNotFoundException(f"Order {reference_id} does not exist")
        event = OrderExportEvent(
            event_id=uuid4(),
            occurred_at=datetime.now(UTC),
            event_type=event_type,
            reference_id=reference_id,
            data=data,
        )
        logger.info(
            "order_export event_id=%s reference_id=%s event_type=%s started",
            event.event_id,
            reference_id,
            event_type,
        )
        try:
            result = await self._salesforce_gateway.send_order(event)
            if (
                result.success is not True
                or result.event_id != event.event_id
                or result.reference_id != reference_id
                or not result.record_id.strip()
            ):
                raise SalesforceRequestException(
                    "Salesforce returned an inconsistent order result"
                )
        except SalesforceRequestException as exc:
            logger.warning(
                "order_export event_id=%s reference_id=%s failed remote_status=%s",
                event.event_id,
                reference_id,
                exc.remote_status,
            )
            raise
        logger.info(
            "order_export event_id=%s reference_id=%s succeeded",
            event.event_id,
            reference_id,
        )
        return result
