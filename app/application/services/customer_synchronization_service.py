from app.application.dtos.customer_integration.events import (
    CustomerIntegrationEvent,
    CustomerSynchronizationResult,
    CustomerUpdatedEvent,
)
from app.application.exceptions import (
    CustomerNotFoundException,
    CustomerSynchronizationConflictException,
    CustomerVersionGapException,
    InvalidCustomerReferenceException,
    StaleCustomerVersionException,
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

                current_version = await work.resource_versions.get_resource_version(
                    reference_id
                )
                if current_version is None:
                    raise InvalidCustomerReferenceException(
                        f"Customer {reference_id} has no synchronization version"
                    )
                if event.resource_version <= current_version:
                    raise StaleCustomerVersionException(
                        f"Customer {reference_id} already reached version "
                        f"{current_version}"
                    )
                if event.resource_version != current_version + 1:
                    raise CustomerVersionGapException(
                        f"Customer {reference_id} expects version "
                        f"{current_version + 1}"
                    )
                await work.customers.update_customer(reference_id, event.data)
            else:
                if event.resource_version != 1:
                    raise CustomerSynchronizationConflictException(
                        "Customer creation requires resource version 1"
                    )
                reference_id = await work.customers.create_customer(event.data)

            result = CustomerSynchronizationResult(
                success=True, reference_id=reference_id
            )
            await work.resource_versions.save_resource_version(
                reference_id, event.resource_version
            )
            await work.processed_events.save_processed_result(event, result)
            await work.commit()

        return result
