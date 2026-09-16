from app.application.dtos.customer_integration.events import (
    CustomerIntegrationEvent,
    CustomerSynchronizationResult,
    CustomerUpdatedEvent,
)


class CustomerSynchronizationService:
    async def synchronize_customer(
        self, event: CustomerIntegrationEvent
    ) -> CustomerSynchronizationResult:
        reference_id = (
            event.reference_id if isinstance(event, CustomerUpdatedEvent) else 42
        )

        return CustomerSynchronizationResult(success=True, reference_id=reference_id)
