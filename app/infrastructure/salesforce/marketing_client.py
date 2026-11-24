"""Send post-order recommendations to the Salesforce Marketing endpoint."""

import httpx

from app.application.dtos.order_cross_sell import (
    OrderCrossSellReceipt,
    OrderCrossSellRequest,
)
from app.application.exceptions import (
    SalesforceRequestException,
    SalesforceTimeoutException,
)
from app.application.ports import SalesforceMarketingGateway

from .auth import get_access_token, invalidate_access_token
from .payload import JsonValue
from .settings import SalesforceSettings


class SalesforceMarketingAPI(SalesforceMarketingGateway):
    def __init__(
        self,
        settings: SalesforceSettings | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings
        self._http_client = http_client

    async def send_order_cross_sell(
        self, request: OrderCrossSellRequest
    ) -> OrderCrossSellReceipt:
        settings = self._settings or SalesforceSettings.load()
        payload: dict[str, JsonValue] = {
            "customer_id": str(request.customer_id),
            "order_id": request.order_id,
            "related_product": [str(product_id) for product_id in request.product_ids],
        }
        if self._http_client is not None:
            return await self._send(self._http_client, settings, payload, request)
        async with httpx.AsyncClient(follow_redirects=False) as client:
            return await self._send(client, settings, payload, request)

    @staticmethod
    async def _post(
        client: httpx.AsyncClient,
        settings: SalesforceSettings,
        payload: dict[str, JsonValue],
        token: str,
    ) -> httpx.Response:
        try:
            return await client.post(
                settings.marketing_products_url,
                json=payload,
                headers={"Authorization": f"Bearer {token}"},
                timeout=settings.timeout_seconds,
                follow_redirects=False,
            )
        except httpx.TimeoutException:
            raise SalesforceTimeoutException(
                "Salesforce Marketing timed out; the result is unknown and the request was not retried"
            ) from None
        except httpx.RequestError:
            raise SalesforceRequestException(
                "Salesforce Marketing delivery failed; the request was not retried"
            ) from None

    async def _send(
        self,
        client: httpx.AsyncClient,
        settings: SalesforceSettings,
        payload: dict[str, JsonValue],
        request: OrderCrossSellRequest,
    ) -> OrderCrossSellReceipt:
        token = await get_access_token(client, settings)
        response = await self._post(client, settings, payload, token)
        if response.status_code == 401:
            invalidate_access_token(settings, token)
            token = await get_access_token(client, settings)
            response = await self._post(client, settings, payload, token)
            if response.status_code == 401:
                invalidate_access_token(settings, token)
        if response.status_code != 201:
            raise SalesforceRequestException(
                f"Salesforce Marketing rejected cross-selling (HTTP {response.status_code})",
                remote_status=response.status_code,
            )
        return _parse_receipt(response, len(request.product_ids))


def _parse_receipt(
    response: httpx.Response, expected_count: int
) -> OrderCrossSellReceipt:
    try:
        body = response.json()
        records = body["recordIds"]
        count = body["recordsCreated"]
        if (
            body["success"] is not True
            or body["flow"] != "recommended_products"
            or type(count) is not int
            or count != expected_count
            or not isinstance(records, list)
            or len(records) != count
            or not all(isinstance(record, str) and record.strip() for record in records)
        ):
            raise ValueError
    except (ValueError, TypeError, KeyError):
        raise SalesforceRequestException(
            "Salesforce Marketing returned an invalid cross-selling result"
        ) from None
    return OrderCrossSellReceipt(tuple(records))
