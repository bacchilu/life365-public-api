"""No transport test contacts Salesforce or obtains real credentials."""

import asyncio
import json
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime
from uuid import UUID

import httpx
import pytest

from app.application.dtos.order_integration import OrderEventType, OrderExportEvent
from app.application.exceptions import (
    SalesforceConfigurationException,
    SalesforceRequestException,
    SalesforceTimeoutException,
)
from app.infrastructure.salesforce import SalesforceOrderAPI, SalesforceSettings, auth
from app.infrastructure.salesforce.order_payload import order_event_payload
from tests.test_order_export_service import order_data

_SETTINGS = SalesforceSettings(
    "https://unit.my.salesforce.com/services/oauth2/token",
    "https://unit.my.salesforce.com/services/apexrest/customer/sync/",
    "test-id",
    "test-secret",
)


@pytest.fixture(autouse=True)
def empty_token_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth, "_access_token", None)
    monkeypatch.setattr(auth, "_credentials_key", None)
    monkeypatch.setattr(auth, "_token_lock", asyncio.Lock())


def event(kind: OrderEventType = "order.created") -> OrderExportEvent:
    return OrderExportEvent(
        UUID("47cbdbb3-751c-49eb-9594-09e12504c8e7"),
        datetime(2026, 11, 6, tzinfo=UTC),
        kind,
        1001,
        None if kind == "order.deleted" else order_data(),
    )


def success(request: httpx.Request) -> httpx.Response:
    body = json.loads(request.content)
    return httpx.Response(
        201,
        json={
            "success": True,
            "eventId": body["eventId"],
            "referenceId": str(body["referenceId"]),
            "recordId": "801-test",
        },
    )


def test_exact_signed_payload_no_version_or_float_or_repeated_discount() -> None:
    payload = order_event_payload(event())
    assert payload["schemaVersion"] == 1 and "resourceVersion" not in payload
    body = json.loads(json.dumps(payload))["data"]
    assert body["orderDate"].endswith("Z")
    assert body["totals"] == {"net": "95.00", "tax": "20.90", "gross": "115.90"}
    assert body["lines"][1]["unitPrice"] == "10.00"
    assert body["lines"][1]["lineTotal"] == "-10.00"
    assert body["lines"][2]["productReferenceId"] == 124
    assert all("discountPercent" not in line for line in body["lines"])
    assert body["invoice"] is None
    assert body["shippingAddress"]["regionName"] == "Forli-Cesena"
    assert "data" not in order_event_payload(event("order.deleted"))


@pytest.mark.anyio
async def test_all_events_use_post_and_share_one_cached_token() -> None:
    calls: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "cached-token"})
        assert (
            request.method == "POST"
            and request.url.path == "/services/apexrest/order/sync/"
        )
        assert request.headers["authorization"] == "Bearer cached-token"
        return success(request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        gateway = SalesforceOrderAPI(_SETTINGS, client)
        for kind in ("order.created", "order.updated", "order.deleted"):
            assert (await gateway.send_order(event(kind))).success
    assert len(calls) == 4


@pytest.mark.anyio
@pytest.mark.parametrize("final_status", [201, 401, 500])
async def test_expired_token_retry_preserves_identical_event(final_status: int) -> None:
    authentications = 0
    deliveries: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal authentications
        if request.url.path.endswith("/token"):
            authentications += 1
            return httpx.Response(
                200, json={"access_token": f"token-{authentications}"}
            )
        deliveries.append(request)
        if len(deliveries) == 1:
            return httpx.Response(401)
        return success(request) if final_status == 201 else httpx.Response(final_status)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        gateway = SalesforceOrderAPI(_SETTINGS, client)
        if final_status == 201:
            await gateway.send_order(event())
        else:
            with pytest.raises(SalesforceRequestException):
                await gateway.send_order(event())
    assert authentications == 2 and len(deliveries) == 2
    assert deliveries[0].content == deliveries[1].content
    assert deliveries[1].headers["authorization"] == "Bearer token-2"
    if final_status == 401:
        assert auth._access_token is None


@pytest.mark.anyio
@pytest.mark.parametrize("status", [400, 403, 404, 409, 429, 500, 503, 307])
async def test_no_other_retry_redirect_or_remote_body_disclosure(status: int) -> None:
    count = 0

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal count
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "secret-token"})
        count += 1
        return httpx.Response(
            status,
            json={"message": "secret-body"},
            headers={"location": "https://other.invalid"},
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handle), follow_redirects=True
    ) as client:
        with pytest.raises(SalesforceRequestException) as caught:
            await SalesforceOrderAPI(_SETTINGS, client).send_order(event())
    assert count == 1 and caught.value.remote_status == status
    assert "secret" not in str(caught.value)


@pytest.mark.anyio
@pytest.mark.parametrize("failure", [httpx.ReadTimeout, httpx.ConnectError])
async def test_transport_failure_is_not_retried(
    failure: type[httpx.RequestError],
) -> None:
    count = 0

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal count
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "token"})
        count += 1
        raise failure("sensitive details", request=request)

    expected = (
        SalesforceTimeoutException
        if failure is httpx.ReadTimeout
        else SalesforceRequestException
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(expected, match="outcome.*unknown"):
            await SalesforceOrderAPI(_SETTINGS, client).send_order(event())
    assert count == 1


@pytest.mark.anyio
@pytest.mark.parametrize(
    "body", [None, [], "wrong", {"success": False}, {"success": True, "eventId": "bad"}]
)
async def test_malformed_response_is_not_success(body: object) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return (
            httpx.Response(200, json={"access_token": "token"})
            if request.url.path.endswith("/token")
            else httpx.Response(201, json=body)
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(SalesforceRequestException, match="invalid order result"):
            await SalesforceOrderAPI(_SETTINGS, client).send_order(event())


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("referenceId", True),
        ("referenceId", "999"),
        ("eventId", "00000000-0000-0000-0000-000000000001"),
        ("recordId", " "),
        ("success", 1),
    ],
)
async def test_response_must_match_submitted_event(field: str, value: object) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "token"})
        body = success(request).json()
        body[field] = value
        return httpx.Response(201, json=body)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(SalesforceRequestException):
            await SalesforceOrderAPI(_SETTINGS, client).send_order(event())


@pytest.mark.parametrize(
    "url",
    [
        "http://unit.my.salesforce.com/order",
        "https://other.invalid/order",
        "https://unit.my.salesforce.com/order?token=secret",
        "https://user:pass@unit.my.salesforce.com/order",
    ],
)
def test_order_url_guard(url: str) -> None:
    with pytest.raises(SalesforceConfigurationException):
        replace(_SETTINGS, order_url=url)


def test_order_url_default_and_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    assert (
        _SETTINGS.order_sync_url
        == "https://unit.my.salesforce.com/services/apexrest/order/sync/"
    )
    monkeypatch.setenv("SALESFORCE_TOKEN_URL", _SETTINGS.token_url)
    monkeypatch.setenv("SALESFORCE_CUSTOMER_SYNC_URL", _SETTINGS.customer_url)
    monkeypatch.setenv("SALESFORCE_PRODUCT_SYNC_URL", "")
    monkeypatch.setenv(
        "SALESFORCE_ORDER_SYNC_URL", "https://unit.my.salesforce.com/custom/order"
    )
    monkeypatch.setenv("SALESFORCE_CLIENT_ID", "test")
    monkeypatch.setenv("SALESFORCE_CLIENT_SECRET", "secret")
    assert SalesforceSettings.load().order_sync_url.endswith("/custom/order")


@pytest.mark.parametrize("field", ["reference_id", "event_type", "data"])
def test_events_are_immutable(field: str) -> None:
    with pytest.raises(FrozenInstanceError):
        setattr(event(), field, None)


def test_events_require_data_and_aware_timestamps() -> None:
    with pytest.raises(ValueError):
        replace(event(), data=None)
    with pytest.raises(ValueError):
        replace(event("order.deleted"), data=order_data())
    with pytest.raises(ValueError):
        replace(event(), occurred_at=datetime(2026, 1, 1))
