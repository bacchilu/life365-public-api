from app.application.dtos.customer_integration.events import (
    CustomerIntegrationEvent,
    CustomerSynchronizationResult,
    CustomerUpdatedEvent,
)
from app.application.exceptions import (
    CustomerNotFoundException,
    InvalidCustomerReferenceException,
)
from app.application.ports import CustomerSynchronizationUnitOfWork


class CustomerSynchronizationService:
    def __init__(self, unit_of_work: CustomerSynchronizationUnitOfWork) -> None:
        self._unit_of_work = unit_of_work

    async def synchronize_customer(
        self, event: CustomerIntegrationEvent
    ) -> CustomerSynchronizationResult:
        async with self._unit_of_work as work:
            processed_result = await work.processed_events.get_processed_result(event)
            if processed_result is not None:
                return processed_result

            if isinstance(event, CustomerUpdatedEvent):
                reference_id = event.reference_id
                if reference_id <= 0:
                    raise InvalidCustomerReferenceException(
                        "Customer reference must be positive"
                    )
                if not await work.customers.customer_exists(reference_id):
                    raise CustomerNotFoundException(
                        f"Customer {reference_id} does not exist"
                    )

                await work.customers.update_customer(reference_id, event.data)
            else:
                reference_id = await work.customers.create_customer(event.data)

            result = CustomerSynchronizationResult(
                success=True, reference_id=reference_id
            )
            await work.processed_events.save_processed_result(event, result)
            await work.commit()

        return result
