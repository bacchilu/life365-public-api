"""Check the saved order before sending caller-selected recommendations."""

from app.application.dtos.order_cross_sell import (
    OrderCrossSellReceipt,
    OrderCrossSellRequest,
)
from app.application.exceptions import (
    OrderCrossSellNotReadyException,
    OrderNotFoundException,
)
from app.application.ports import OrderCrossSellReader, SalesforceMarketingGateway


class OrderCrossSellService:
    def __init__(
        self, reader: OrderCrossSellReader, gateway: SalesforceMarketingGateway
    ) -> None:
        self._reader = reader
        self._gateway = gateway

    async def send(
        self, order_id: int, product_ids: tuple[int, ...]
    ) -> OrderCrossSellReceipt:
        state = await self._reader.get_cross_sell_state(order_id)
        if state is None:
            raise OrderNotFoundException(f"Order {order_id} does not exist")
        if (
            state.logistic_state != "ACCEPTED"
            or state.invoice_number is None
            or state.invoice_number <= 0
        ):
            raise OrderCrossSellNotReadyException(
                "Cross-selling requires an ACCEPTED order with a positive invoice number"
            )
        if state.customer_id is None or state.customer_id <= 0:
            raise OrderCrossSellNotReadyException(
                "Cross-selling requires an order with a valid customer"
            )
        request = OrderCrossSellRequest(order_id, state.customer_id, product_ids)
        return await self._gateway.send_order_cross_sell(request)
