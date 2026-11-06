"""Send one order event; renew and retry only after an explicit HTTP 401."""

from uuid import UUID

import httpx

from app.application.dtos.order_integration import OrderExportEvent, OrderExportResult
from app.application.exceptions import (
    SalesforceRequestException,
    SalesforceTimeoutException,
)
from app.application.ports import SalesforceOrderGateway

from .auth import get_access_token, invalidate_access_token
from .order_payload import order_event_payload
from .payload import JsonValue
from .settings import SalesforceSettings


class SalesforceOrderAPI(SalesforceOrderGateway):
    def __init__(
        self, settings: SalesforceSettings, http_client: httpx.AsyncClient | None = None
    ) -> None:
        self._settings = settings
        self._http_client = http_client

    async def send_order(self, event: OrderExportEvent) -> OrderExportResult:
        payload = order_event_payload(event)
        if self._http_client is not None:
            return await self._send(self._http_client, event, payload)
        async with httpx.AsyncClient(follow_redirects=False) as client:
            return await self._send(client, event, payload)

    async def _post(
        self, client: httpx.AsyncClient, payload: dict[str, JsonValue], token: str
    ) -> httpx.Response:
        try:
            return await client.post(
                self._settings.order_sync_url,
                json=payload,
                headers={"Authorization": f"Bearer {token}"},
                timeout=self._settings.timeout_seconds,
                follow_redirects=False,
            )
        except httpx.TimeoutException:
            raise SalesforceTimeoutException(
                "Salesforce order delivery timed out; the remote outcome is unknown and the event was not retried"
            ) from None
        except httpx.RequestError:
            raise SalesforceRequestException(
                "Salesforce order delivery failed; the remote outcome may be unknown and the event was not retried"
            ) from None

    async def _send(
        self,
        client: httpx.AsyncClient,
        event: OrderExportEvent,
        payload: dict[str, JsonValue],
    ) -> OrderExportResult:
        token = await get_access_token(client, self._settings)
        response = await self._post(client, payload, token)
        if response.status_code == 401:
            invalidate_access_token(self._settings, token)
            token = await get_access_token(client, self._settings)
            response = await self._post(client, payload, token)
            if response.status_code == 401:
                invalidate_access_token(self._settings, token)
        if response.status_code not in (200, 201):
            raise SalesforceRequestException(
                f"Salesforce rejected the order event (HTTP {response.status_code})",
                remote_status=response.status_code,
            )
        try:
            body = response.json()
            reference = body["referenceId"]
            if type(reference) is int:
                reference_id = reference
            elif (
                isinstance(reference, str)
                and reference.isascii()
                and reference.isdigit()
            ):
                reference_id = int(reference)
            else:
                raise ValueError
            if (
                body["success"] is not True
                or UUID(body["eventId"]) != event.event_id
                or reference_id != event.reference_id
                or not isinstance(body["recordId"], str)
                or not body["recordId"].strip()
            ):
                raise ValueError
        except (ValueError, TypeError, KeyError, AttributeError):
            raise SalesforceRequestException(
                "Salesforce returned an invalid order result"
            ) from None
        return OrderExportResult(True, event.event_id, reference_id, body["recordId"])
