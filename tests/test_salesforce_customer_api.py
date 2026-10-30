"""Outbound HTTP and token lifecycle tests use only httpx.MockTransport."""

import asyncio
import json
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from urllib.parse import parse_qs
from uuid import UUID

import httpx
import pytest

from app.application.dtos.customer_integration.events import CustomerEventType
from app.application.dtos.customer_integration.export import CustomerExportEvent
from app.application.exceptions import (
    InvalidCustomerDataException,
    SalesforceConfigurationException,
    SalesforceRequestException,
    SalesforceTimeoutException,
)
from app.infrastructure.salesforce import (
    SalesforceCustomerAPI,
    SalesforceSettings,
    auth,
)
from app.infrastructure.salesforce.payload import customer_event_payload
from tests.test_customer_export_service import customer_data

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


def _event() -> CustomerExportEvent:
    return CustomerExportEvent(
        event_id=UUID("870815cb-9ebe-40bd-8c1e-ae19e221b44f"),
        occurred_at=datetime(2026, 10, 27, 10, tzinfo=UTC),
        reference_id=42,
        event_type="customer.created",
        data=customer_data(),
    )


def _success(request: httpx.Request) -> httpx.Response:
    payload = json.loads(request.content)
    return httpx.Response(
        201,
        json={
            "success": True,
            "eventId": payload["eventId"],
            "referenceId": str(payload["referenceId"]),
            "accountId": "001-test",
            "message": "Customer synchronized.",
        },
    )


@pytest.mark.anyio
async def test_shared_module_token_is_reused_across_adapters() -> None:
    calls: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path.endswith("/token"):
            assert parse_qs(request.content.decode()) == {
                "grant_type": ["client_credentials"],
                "client_id": ["test-client-id"],
                "client_secret": ["test-client-secret"],
            }
            return httpx.Response(200, json={"access_token": "shared-token"})
        assert request.method == "POST"
        assert request.headers["authorization"] == "Bearer shared-token"
        return _success(request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        first = await SalesforceCustomerAPI(_SETTINGS, client).send_customer(_event())
        second = await SalesforceCustomerAPI(_SETTINGS, client).send_customer(
            replace(_event(), event_type="customer.updated")
        )
    assert first.success and second.success
    assert len(calls) == 3 and auth._access_token == "shared-token"
    assert json.loads(calls[2].content)["data"] == json.loads(calls[1].content)["data"]


@pytest.mark.anyio
@pytest.mark.parametrize("final_status", [201, 401, 500])
async def test_401_renews_once_and_reuses_the_exact_event(final_status: int) -> None:
    token_calls = 0
    deliveries: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal token_calls
        if request.url.path.endswith("/token"):
            token_calls += 1
            return httpx.Response(200, json={"access_token": f"token-{token_calls}"})
        deliveries.append(request)
        if len(deliveries) == 1:
            return httpx.Response(401, json=[{"errorCode": "INVALID_SESSION_ID"}])
        return (
            _success(request) if final_status == 201 else httpx.Response(final_status)
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        gateway = SalesforceCustomerAPI(_SETTINGS, client)
        if final_status == 201:
            assert (await gateway.send_customer(_event())).success
        else:
            with pytest.raises(SalesforceRequestException):
                await gateway.send_customer(_event())
    assert token_calls == 2 and len(deliveries) == 2
    assert deliveries[0].content == deliveries[1].content
    assert deliveries[0].headers["authorization"] == "Bearer token-1"
    assert deliveries[1].headers["authorization"] == "Bearer token-2"
    if final_status == 401:
        assert auth._access_token is None


@pytest.mark.anyio
@pytest.mark.parametrize("status", [400, 403, 404, 409, 429, 500, 503, 307])
async def test_other_errors_are_not_retried_or_leaked(status: int) -> None:
    deliveries = 0

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal deliveries
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "sensitive-token"})
        deliveries += 1
        return httpx.Response(
            status,
            json={"detail": "sensitive remote body"},
            headers={"location": "https://elsewhere.invalid"},
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handle), follow_redirects=True
    ) as client:
        with pytest.raises(SalesforceRequestException) as caught:
            await SalesforceCustomerAPI(_SETTINGS, client).send_customer(_event())
    assert deliveries == 1 and caught.value.remote_status == status
    assert "sensitive" not in str(caught.value)


@pytest.mark.anyio
async def test_timeout_is_not_retried_and_marks_outcome_unknown() -> None:
    deliveries = 0

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal deliveries
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "token"})
        deliveries += 1
        raise httpx.ReadTimeout("sensitive remote details", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(SalesforceTimeoutException, match="outcome is unknown"):
            await SalesforceCustomerAPI(_SETTINGS, client).send_customer(_event())
    assert deliveries == 1


@pytest.mark.anyio
@pytest.mark.parametrize(
    "body",
    [{"success": False}, {"success": True, "eventId": "invalid"}, [], "unexpected"],
)
async def test_malformed_success_is_rejected(body: object) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return (
            httpx.Response(200, json={"access_token": "token"})
            if request.url.path.endswith("/token")
            else httpx.Response(201, json=body)
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(SalesforceRequestException, match="invalid customer result"):
            await SalesforceCustomerAPI(_SETTINGS, client).send_customer(_event())


@pytest.mark.anyio
async def test_concurrent_calls_share_one_authentication() -> None:
    tokens = 0

    async def handle(request: httpx.Request) -> httpx.Response:
        nonlocal tokens
        if request.url.path.endswith("/token"):
            tokens += 1
            await asyncio.sleep(0)
            return httpx.Response(200, json={"access_token": "shared-token"})
        return _success(request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        gateway = SalesforceCustomerAPI(_SETTINGS, client)
        await asyncio.gather(
            gateway.send_customer(_event()), gateway.send_customer(_event())
        )
    assert tokens == 1


def test_payload_preserves_the_complete_contract_and_extension_keys() -> None:
    event = _event()
    payload = customer_event_payload(event)
    assert payload["schemaVersion"] == 1 and payload["referenceId"] == 42
    assert "resourceVersion" not in payload
    data = payload["data"]
    assert isinstance(data, dict)
    assert set(data) == {
        "credentials",
        "company",
        "primaryContact",
        "billingAddress",
        "delivery",
        "taxProfile",
        "communicationPreferences",
        "registration",
        "commercial",
        "banking",
        "shop",
        "operationalSettings",
        "notes",
        "extensions",
    }
    commercial = data["commercial"]
    assert isinstance(commercial, dict)
    assert commercial["creditGranted"] == "10000.00"
    extra = replace(
        event.data.extensions,
        parameters={"snake_case": {"keep_false": False, "zero": 0, "items": []}},
    )
    exported = customer_event_payload(
        replace(event, data=replace(event.data, extensions=extra))
    )
    extensions = exported["data"]
    assert isinstance(extensions, dict)
    assert extensions["extensions"] == {
        "parameters": extra.parameters,
        "extraData": None,
    }
    assert "initial-customer-password" not in repr(event)


@pytest.mark.parametrize("event_type", ["customer.created", "customer.updated"])
@pytest.mark.parametrize("privacy", [None, False, True])
@pytest.mark.parametrize("rules", [None, False, True])
def test_only_null_privacy_and_rules_are_exported_as_false(
    event_type: CustomerEventType, privacy: bool | None, rules: bool | None
) -> None:
    event = _event()
    preferences = replace(
        event.data.communication_preferences,
        newsletter=None,
        privacy_registered=privacy,
        rules_registered=rules,
    )
    event = replace(
        event,
        event_type=event_type,
        data=replace(
            event.data,
            communication_preferences=preferences,
            company=replace(event.data.company, website=None),
            extensions=replace(
                event.data.extensions,
                parameters={"privacyRegistered": None, "rulesRegistered": None},
            ),
        ),
    )

    payload = customer_event_payload(event)

    data = payload["data"]
    assert isinstance(data, dict)
    assert data["communicationPreferences"] == {
        "newsletter": None,
        "privacyRegistered": privacy if privacy is not None else False,
        "rulesRegistered": rules if rules is not None else False,
    }
    company = data["company"]
    assert isinstance(company, dict)
    assert company["website"] is None
    assert data["extensions"] == {
        "parameters": {"privacyRegistered": None, "rulesRegistered": None},
        "extraData": None,
    }
    assert event.data.communication_preferences is preferences
    assert preferences.privacy_registered is privacy
    assert preferences.rules_registered is rules


@pytest.mark.anyio
@pytest.mark.parametrize("event_type", ["customer.created", "customer.updated"])
async def test_http_delivery_converts_null_privacy_and_rules_to_false(
    event_type: CustomerEventType,
) -> None:
    event = _event()
    event = replace(
        event,
        event_type=event_type,
        data=replace(
            event.data,
            communication_preferences=replace(
                event.data.communication_preferences,
                privacy_registered=None,
                rules_registered=None,
            ),
        ),
    )
    deliveries = 0

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal deliveries
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "test-token"})
        deliveries += 1
        preferences = json.loads(request.content)["data"]["communicationPreferences"]
        assert preferences["privacyRegistered"] is False
        assert preferences["rulesRegistered"] is False
        return _success(request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        result = await SalesforceCustomerAPI(_SETTINGS, client).send_customer(event)

    assert result.success is True and deliveries == 1
    assert event.data.communication_preferences.privacy_registered is None
    assert event.data.communication_preferences.rules_registered is None


@pytest.mark.parametrize(
    "value", [Decimal("1.001"), Decimal("NaN"), Decimal("Infinity")]
)
def test_financial_serialization_never_rounds(value: Decimal) -> None:
    event = _event()
    commercial = replace(event.data.commercial, credit_value=value)
    with pytest.raises(InvalidCustomerDataException):
        customer_event_payload(
            replace(event, data=replace(event.data, commercial=commercial))
        )


def test_configuration_validates_urls_and_hides_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for url in (
        "http://unit.my.salesforce.com/api",
        "https://different.invalid/api",
        "https://user:secret@unit.my.salesforce.com/api",
    ):
        with pytest.raises(SalesforceConfigurationException):
            replace(_SETTINGS, customer_url=url)
    assert _SETTINGS.client_secret not in repr(_SETTINGS)
    monkeypatch.setenv("SALESFORCE_TOKEN_URL", _SETTINGS.token_url)
    monkeypatch.setenv("SALESFORCE_CLIENT_ID", _SETTINGS.client_id)
    monkeypatch.setenv("SALESFORCE_CLIENT_SECRET", _SETTINGS.client_secret)
    monkeypatch.setenv("SALESFORCE_CUSTOMER_SYNC_URL", "")
    assert SalesforceSettings.load().customer_url == _SETTINGS.customer_url


@pytest.mark.anyio
@pytest.mark.parametrize("status", [400, 401, 500])
async def test_authentication_failure_never_sends_an_event(status: int) -> None:
    calls: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(status, json={"error": "sensitive authentication body"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(SalesforceRequestException) as caught:
            await SalesforceCustomerAPI(_SETTINGS, client).send_customer(_event())
    assert calls == ["/services/oauth2/token"]
    assert auth._access_token is None
    assert "sensitive" not in str(caught.value)


@pytest.mark.anyio
@pytest.mark.parametrize("field", ["eventId", "referenceId", "success", "accountId"])
async def test_success_must_match_the_submitted_event(field: str) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "token"})
        result = _success(request).json()
        result[field] = {
            "eventId": "00000000-0000-0000-0000-000000000001",
            "referenceId": "99",
            "success": False,
            "accountId": " ",
        }[field]
        return httpx.Response(201, json=result)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(SalesforceRequestException, match="invalid customer result"):
            await SalesforceCustomerAPI(_SETTINGS, client).send_customer(_event())


@pytest.mark.anyio
async def test_different_credentials_cannot_reuse_another_cached_token() -> None:
    authentications: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            client_id = parse_qs(request.content.decode())["client_id"][0]
            authentications.append(client_id)
            return httpx.Response(200, json={"access_token": client_id})
        return _success(request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        await SalesforceCustomerAPI(_SETTINGS, client).send_customer(_event())
        await SalesforceCustomerAPI(
            replace(_SETTINGS, client_id="different-client"), client
        ).send_customer(_event())
    assert authentications == ["test-client-id", "different-client"]
