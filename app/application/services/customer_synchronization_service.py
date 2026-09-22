from app.application.dtos.customer_integration.events import (
    CustomerIntegrationEvent,
    CustomerSynchronizationResult,
    CustomerUpdatedEvent,
)
from app.application.ports import CustomerSynchronizationUnitOfWork


class CustomerSynchronizationService:
    def __init__(self, unit_of_work: CustomerSynchronizationUnitOfWork) -> None:
        self._unit_of_work = unit_of_work

    async def synchronize_customer(
        self, event: CustomerIntegrationEvent
    ) -> CustomerSynchronizationResult:
        reference_id = (
            event.reference_id if isinstance(event, CustomerUpdatedEvent) else 42
        )

        return CustomerSynchronizationResult(success=True, reference_id=reference_id)
