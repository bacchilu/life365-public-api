"""Send a current product snapshot or a remote-only deactivation."""

import logging
from datetime import UTC, datetime
from uuid import uuid4

from app.application.dtos.product_integration import (
    ProductEventType,
    ProductExportEvent,
    ProductExportResult,
)
from app.application.exceptions import (
    InvalidProductReferenceException,
    ProductNotFoundException,
    SalesforceRequestException,
)
from app.application.ports import ProductExportReader, SalesforceProductGateway

logger = logging.getLogger(__name__)


class ProductExportService:
    def __init__(
        self, reader: ProductExportReader, salesforce_gateway: SalesforceProductGateway
    ) -> None:
        self._reader = reader
        self._salesforce_gateway = salesforce_gateway

    async def export_product(
        self, reference_id: int, event_type: ProductEventType
    ) -> ProductExportResult:
        if type(reference_id) is not int or reference_id <= 0:
            raise InvalidProductReferenceException("Product reference must be positive")
        if event_type not in ("product.created", "product.updated", "product.deleted"):
            raise ValueError("Unsupported product export event type")
        data = None
        if event_type == "product.deleted":
            exists = await self._reader.product_exists(reference_id)
        else:
            data = await self._reader.get_product(reference_id)
            exists = data is not None
        if not exists:
            raise ProductNotFoundException(f"Product {reference_id} does not exist")
        event = ProductExportEvent(
            event_id=uuid4(),
            occurred_at=datetime.now(UTC),
            event_type=event_type,
            reference_id=reference_id,
            data=data,
        )
        logger.info(
            "product_export event_id=%s reference_id=%s event_type=%s started",
            event.event_id,
            reference_id,
            event_type,
        )
        try:
            result = await self._salesforce_gateway.send_product(event)
            if (
                result.success is not True
                or result.event_id != event.event_id
                or result.reference_id != reference_id
                or not result.record_id.strip()
            ):
                raise SalesforceRequestException(
                    "Salesforce returned an inconsistent product result"
                )
        except SalesforceRequestException as exc:
            logger.warning(
                "product_export event_id=%s reference_id=%s failed remote_status=%s",
                event.event_id,
                reference_id,
                exc.remote_status,
            )
            raise
        logger.info(
            "product_export event_id=%s reference_id=%s succeeded",
            event.event_id,
            reference_id,
        )
        return result
