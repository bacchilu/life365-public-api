"""Check inactivity before sending caller-selected recommendations."""

from app.application.dtos.customer_reactivation import (
    CustomerReactivationReceipt,
    CustomerReactivationRequest,
)
from app.application.exceptions import (
    CustomerNotFoundException,
    CustomerReactivationNotReadyException,
)
from app.application.ports import (
    CustomerReactivationReader,
    SalesforceCustomerReactivationGateway,
)


class CustomerReactivationService:
    def __init__(
        self,
        reader: CustomerReactivationReader,
        gateway: SalesforceCustomerReactivationGateway,
    ) -> None:
        self._reader = reader
        self._gateway = gateway

    async def send(
        self, request: CustomerReactivationRequest
    ) -> CustomerReactivationReceipt:
        inactive = await self._reader.is_inactive(request.customer_id)
        if inactive is None:
            raise CustomerNotFoundException(
                f"Customer {request.customer_id} does not exist"
            )
        if not inactive:
            raise CustomerReactivationNotReadyException(
                "Reactivation requires a qualifying last order older than 90 days"
            )
        return await self._gateway.send_customer_reactivation(request)
