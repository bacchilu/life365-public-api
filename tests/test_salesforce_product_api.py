"""Salesforce transport tests are isolated from all live business endpoints."""

import asyncio
import json
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime
from uuid import UUID

import httpx
import pytest

from app.application.dtos.customer_integration.export import CustomerExportEvent
from app.application.dtos.product_integration import (
    ProductEventType,
    ProductExportEvent,
)
from app.application.exceptions import (
    SalesforceConfigurationException,
    SalesforceRequestException,
    SalesforceTimeoutException,
)
from app.infrastructure.salesforce import (
    SalesforceCustomerAPI,
    SalesforceProductAPI,
    SalesforceSettings,
    auth,
)
from app.infrastructure.salesforce.product_payload import product_event_payload
from tests.test_customer_export_service import customer_data
from tests.test_product_export_service import product_data

_SETTINGS = SalesforceSettings(
    "https://unit.my.salesforce.com/services/oauth2/token",
    "https://unit.my.salesforce.com/services/apexrest/customer/sync/",
    "test-client-id",
    "test-client-secret",
)


@pytest.fixture(autouse=True)
def empty_token_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth, "_access_token", None)
    monkeypatch.setattr(auth, "_credentials_key", None)
    monkeypatch.setattr(auth, "_token_lock", asyncio.Lock())


def _event(kind: ProductEventType = "product.created") -> ProductExportEvent:
    return ProductExportEvent(
        UUID("3f8f7903-9336-45dd-8843-e4e8bc1391c0"),
        datetime(2026, 11, 3, 12, tzinfo=UTC),
        kind,
        101,
        None if kind == "product.deleted" else product_data(),
    )


def _success(request: httpx.Request) -> httpx.Response:
    payload = json.loads(request.content)
    return httpx.Response(
        201,
        json={
            "success": True,
            "eventId": payload["eventId"],
            "referenceId": str(payload["referenceId"]),
            "recordId": "01t-test",
        },
    )


@pytest.mark.anyio
async def test_all_events_use_post_and_one_cached_token() -> None:
    calls: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "shared-token"})
        assert request.method == "POST"
        assert request.url.path == "/services/apexrest/product/sync/"
        assert request.headers["authorization"] == "Bearer shared-token"
        return _success(request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        gateway = SalesforceProductAPI(_SETTINGS, client)
        for kind in ("product.created", "product.updated", "product.deleted"):
            assert (await gateway.send_product(_event(kind))).success
    assert len(calls) == 4
    assert "data" not in json.loads(calls[-1].content)
    assert json.loads(calls[1].content)["data"] == json.loads(calls[2].content)["data"]


@pytest.mark.anyio
@pytest.mark.parametrize("final_status", [201, 401, 500])
async def test_expired_token_is_renewed_once_with_identical_event(
    final_status: int,
) -> None:
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
        return (
            _success(request) if final_status == 201 else httpx.Response(final_status)
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        gateway = SalesforceProductAPI(_SETTINGS, client)
        if final_status == 201:
            assert (await gateway.send_product(_event())).success
        else:
            with pytest.raises(SalesforceRequestException):
                await gateway.send_product(_event())
    assert authentications == 2 and len(deliveries) == 2
    assert deliveries[0].content == deliveries[1].content
    assert deliveries[1].headers["authorization"] == "Bearer token-2"
    if final_status == 401:
        assert auth._access_token is None


@pytest.mark.anyio
@pytest.mark.parametrize("status", [400, 403, 404, 409, 429, 500, 503, 307])
async def test_other_errors_are_not_retried_and_bodies_are_not_leaked(
    status: int,
) -> None:
    deliveries = 0

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal deliveries
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "secret-token"})
        deliveries += 1
        return httpx.Response(
            status,
            json={"message": "secret-remote-body"},
            headers={"location": "https://other.invalid"},
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handle), follow_redirects=True
    ) as client:
        with pytest.raises(SalesforceRequestException) as caught:
            await SalesforceProductAPI(_SETTINGS, client).send_product(_event())
    assert deliveries == 1 and caught.value.remote_status == status
    assert "secret" not in str(caught.value)


@pytest.mark.anyio
@pytest.mark.parametrize("failure", [httpx.ReadTimeout, httpx.ConnectError])
async def test_transport_failure_has_unknown_outcome_and_is_not_retried(
    failure: type[httpx.RequestError],
) -> None:
    deliveries = 0

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal deliveries
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "token"})
        deliveries += 1
        raise failure("sensitive details", request=request)

    expected = (
        SalesforceTimeoutException
        if failure is httpx.ReadTimeout
        else SalesforceRequestException
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(expected, match="outcome.*unknown"):
            await SalesforceProductAPI(_SETTINGS, client).send_product(_event())
    assert deliveries == 1


@pytest.mark.anyio
@pytest.mark.parametrize(
    "body", [None, [], "wrong", {"success": False}, {"success": True, "eventId": "bad"}]
)
async def test_malformed_success_is_rejected(body: object) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return (
            httpx.Response(200, json={"access_token": "token"})
            if request.url.path.endswith("/token")
            else httpx.Response(201, json=body)
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(SalesforceRequestException, match="invalid product result"):
            await SalesforceProductAPI(_SETTINGS, client).send_product(_event())


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("eventId", "00000000-0000-0000-0000-000000000001"),
        ("referenceId", True),
        ("referenceId", "999"),
        ("recordId", " "),
        ("success", 1),
    ],
)
async def test_response_must_correspond_to_the_submitted_event(
    field: str, value: object
) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "token"})
        body = _success(request).json()
        body[field] = value
        return httpx.Response(201, json=body)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(SalesforceRequestException, match="invalid product result"):
            await SalesforceProductAPI(_SETTINGS, client).send_product(_event())


@pytest.mark.anyio
async def test_products_and_customers_share_the_oauth_cache() -> None:
    authentications = 0

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal authentications
        if request.url.path.endswith("/token"):
            authentications += 1
            return httpx.Response(200, json={"access_token": "shared-token"})
        if "/product/" in request.url.path:
            return _success(request)
        body = _success(request).json()
        body["accountId"] = body.pop("recordId")
        return httpx.Response(201, json=body)

    customer = CustomerExportEvent(
        event_id=_event().event_id,
        occurred_at=_event().occurred_at,
        event_type="customer.created",
        reference_id=1,
        data=customer_data(),
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        await SalesforceCustomerAPI(_SETTINGS, client).send_customer(customer)
        await SalesforceProductAPI(_SETTINGS, client).send_product(_event())
    assert authentications == 1


def test_full_snapshot_serialization_preserves_nulls_and_false() -> None:
    original = _event()
    assert original.data is not None
    event = replace(
        original,
        data=replace(
            original.data,
            active=False,
            ean=None,
            brand=None,
            category=None,
            image_url=None,
        ),
    )
    payload = product_event_payload(event)
    assert set(payload) == {
        "schemaVersion",
        "eventId",
        "occurredAt",
        "eventType",
        "referenceId",
        "data",
    }
    data = payload["data"]
    assert isinstance(data, dict)
    assert set(data) == {
        "sku",
        "name",
        "description",
        "brand",
        "ean",
        "category",
        "productUrl",
        "imageUrl",
        "active",
    }
    assert data["active"] is False
    assert data["ean"] is data["brand"] is data["category"] is data["imageUrl"] is None
    assert (
        payload["occurredAt"] == "2026-11-03T12:00:00Z"
        and payload["schemaVersion"] == 1
    )
    assert "resourceVersion" not in payload


def test_dto_rejects_mismatched_event_data_and_naive_timestamps() -> None:
    event = _event()
    with pytest.raises(ValueError):
        replace(event, data=None)
    with pytest.raises(ValueError):
        replace(event, event_type="product.deleted")
    with pytest.raises(ValueError):
        replace(event, occurred_at=datetime(2026, 11, 3))


@pytest.mark.parametrize("field", ["reference_id", "event_type", "data"])
def test_product_events_are_immutable(field: str) -> None:
    with pytest.raises(FrozenInstanceError):
        setattr(_event(), field, None)


@pytest.mark.anyio
async def test_optional_fields_can_be_sent_as_null() -> None:
    event = _event()
    assert event.data is not None
    event = replace(
        event,
        data=replace(event.data, category=None, ean=None, brand=None, image_url=None),
    )

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "token"})
        data = json.loads(request.content)["data"]
        assert (
            data["category"] is data["ean"] is data["brand"] is data["imageUrl"] is None
        )
        return _success(request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        assert (
            await SalesforceProductAPI(_SETTINGS, client).send_product(event)
        ).success


@pytest.mark.parametrize(
    "url",
    [
        "http://unit.my.salesforce.com/api",
        "https://different.invalid/api",
        "https://user:password@unit.my.salesforce.com/api",
        "https://unit.my.salesforce.com/api?secret=value",
        "https://unit.my.salesforce.com:invalid/api",
    ],
)
def test_product_endpoint_configuration_rejects_unsafe_origins(url: str) -> None:
    with pytest.raises(SalesforceConfigurationException):
        replace(_SETTINGS, product_url=url)


def test_optional_product_url_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    assert (
        _SETTINGS.product_sync_url
        == "https://unit.my.salesforce.com/services/apexrest/product/sync/"
    )
    for key, value in {
        "SALESFORCE_TOKEN_URL": _SETTINGS.token_url,
        "SALESFORCE_CLIENT_ID": _SETTINGS.client_id,
        "SALESFORCE_CLIENT_SECRET": _SETTINGS.client_secret,
        "SALESFORCE_CUSTOMER_SYNC_URL": _SETTINGS.customer_url,
        "SALESFORCE_PRODUCT_SYNC_URL": "https://unit.my.salesforce.com/custom-product/",
    }.items():
        monkeypatch.setenv(key, value)
    assert SalesforceSettings.load().product_sync_url.endswith("/custom-product/")
