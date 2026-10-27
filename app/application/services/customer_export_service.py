"""Synchronously export current customer data without persistence or retries."""

import logging
from datetime import UTC, datetime
from uuid import uuid4

from app.application.dtos.customer_integration.events import CustomerEventType
from app.application.dtos.customer_integration.export import (
    CustomerExportEvent,
    CustomerExportResult,
)
from app.application.exceptions import (
    CustomerNotFoundException,
    InvalidCustomerReferenceException,
    SalesforceRequestException,
)
from app.application.ports import CustomerExportReader, SalesforceCustomerGateway

logger = logging.getLogger(__name__)


class CustomerExportService:
    def __init__(
        self,
        reader: CustomerExportReader,
        salesforce_gateway: SalesforceCustomerGateway,
    ) -> None:
        self._reader = reader
        self._salesforce_gateway = salesforce_gateway

    async def export_customer(
        self, reference_id: int, event_type: CustomerEventType
    ) -> CustomerExportResult:
        if type(reference_id) is not int or reference_id <= 0:
            raise InvalidCustomerReferenceException(
                "Customer reference must be positive"
            )
        if event_type not in ("customer.created", "customer.updated"):
            raise ValueError("Unsupported customer export event type")
        data = await self._reader.get_customer(reference_id)
        if data is None:
            raise CustomerNotFoundException(f"Customer {reference_id} does not exist")
        event = CustomerExportEvent(
            event_id=uuid4(),
            occurred_at=datetime.now(UTC),
            event_type=event_type,
            reference_id=reference_id,
            data=data,
        )
        logger.info(
            "customer_export event_id=%s reference_id=%s event_type=%s started",
            event.event_id,
            reference_id,
            event_type,
        )
        try:
            result = await self._salesforce_gateway.send_customer(event)
            if (
                result.success is not True
                or result.event_id != event.event_id
                or result.reference_id != reference_id
                or not result.account_id.strip()
            ):
                raise SalesforceRequestException(
                    "Salesforce returned an inconsistent customer result"
                )
        except SalesforceRequestException as exc:
            logger.warning(
                "customer_export event_id=%s reference_id=%s failed remote_status=%s",
                event.event_id,
                reference_id,
                exc.remote_status,
            )
            raise
        logger.info(
            "customer_export event_id=%s reference_id=%s succeeded",
            event.event_id,
            reference_id,
        )
        return result
