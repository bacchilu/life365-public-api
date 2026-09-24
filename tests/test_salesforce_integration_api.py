import json
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import TypeAdapter, ValidationError

os.environ.setdefault("DATABASE_URL", "postgresql://localhost/test")
os.environ.setdefault(
    "JWT_SECRET_KEY",
    "test-secret-key-with-at-least-32-bytes",
)

import app.api.integrations.routes as integration_routes
from app.api.dependencies import get_auth_service
from app.api.integrations.converters.events import convert_customer_event
from app.api.integrations.routes import SalesforceEventRequest
from app.api.integrations.schemas.customer import (
    IntegrationCustomerData as ApiIntegrationCustomerData,
)
from app.application.domain import (
    AuthenticatedUser,
    PrincipalType,
    Role,
    resolve_permissions,
    resolve_product_access_policy,
)
from app.application.exceptions import AuthenticationException, DBException
from app.application.services.customer_synchronization_service import (
    CustomerSynchronizationService,
)
from app.infrastructure.data_mapper.customer_synchronization import (
    InMemoryCustomerSynchronizationStore,
    InMemoryCustomerSynchronizationUnitOfWork,
)
from app.main import app

_FIXTURE_PATH = (
    Path(__file__).resolve().parent
    / "fixtures/integrations/salesforce/customer-created-v1.json"
)
_EVENT_ADAPTER = TypeAdapter(SalesforceEventRequest)
_URL = "/integrations/salesforce/events"
_HEADERS = {"Authorization": "Bearer valid-token"}


class FakeAuthService:
    def __init__(self, user: AuthenticatedUser) -> None:
        self.user = user
        self.validated_tokens: list[str | None] = []

    async def validate_token(self, token: str | None) -> AuthenticatedUser:
        self.validated_tokens.append(token)
        if token != "valid-token":
            raise AuthenticationException("Invalid credentials")
        return self.user


@pytest.fixture
def store() -> Iterator[InMemoryCustomerSynchronizationStore]:
    store = InMemoryCustomerSynchronizationStore()

    async def override_service() -> CustomerSynchronizationService:
        return CustomerSynchronizationService(
            InMemoryCustomerSynchronizationUnitOfWork(store)
        )

    app.dependency_overrides[
        integration_routes.get_customer_synchronization_service
    ] = override_service
    try:
        yield store
    finally:
        app.dependency_overrides.pop(
            integration_routes.get_customer_synchronization_service, None
        )
        app.dependency_overrides.pop(get_auth_service, None)


def _authenticate_as(role: Role) -> FakeAuthService:
    user = AuthenticatedUser(
        id=1,
        username=role.value,
        role=role,
        principal_type=(
            PrincipalType.CUSTOMER if role is Role.CUSTOMER else PrincipalType.USER
        ),
        token_id="token-id",
        permissions=resolve_permissions(role),
        product_access=resolve_product_access_policy(role, user_id=1),
    )
    auth_service = FakeAuthService(user)

    async def override_auth_service() -> FakeAuthService:
        return auth_service

    app.dependency_overrides[get_auth_service] = override_auth_service
    return auth_service


def _create_payload() -> dict[str, Any]:
    return json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))


def _update_payload(reference_id: int) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "eventId": "726c7c74-287d-44f2-b060-81fefa3d235e",
        "occurredAt": "2026-09-16T10:00:00Z",
        "eventType": "customer.updated",
        "resourceVersion": 2,
        "referenceId": reference_id,
        "data": {
            "company": {"website": None, "primaryPhone": ""},
            "communicationPreferences": {"newsletter": False},
            "commercial": {"paymentDays": 0},
            "notes": {"items": []},
        },
    }


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    )


def test_salesforce_event_rejects_customer_deletion() -> None:
    with pytest.raises(ValidationError):
        _EVENT_ADAPTER.validate_python(
            {
                "schemaVersion": 1,
                "eventId": "726c7c74-287d-44f2-b060-81fefa3d235d",
                "occurredAt": "2026-09-04T10:00:00Z",
                "eventType": "customer.deleted",
                "referenceId": 42,
            }
        )


@pytest.mark.anyio
async def test_admin_can_create_and_update_a_customer(
    store: InMemoryCustomerSynchronizationStore,
) -> None:
    auth_service = _authenticate_as(Role.ADMIN)
    created_payload = _create_payload()
    request = _EVENT_ADAPTER.validate_python(created_payload)

    assert isinstance(request.data, ApiIntegrationCustomerData)
    assert request.data.credentials.login == "acme-italia"
    assert request.data.company.name == "ACME Italia SRL"

    async with _client() as client:
        created = await client.post(_URL, json=created_payload, headers=_HEADERS)
        updated_payload = _update_payload(1)
        updated = await client.post(_URL, json=updated_payload, headers=_HEADERS)

    assert created.status_code == 200
    assert created.json() == {
        "success": True,
        "eventId": created_payload["eventId"],
        "referenceId": 1,
    }
    assert updated.status_code == 200
    assert updated.json() == {
        "success": True,
        "eventId": updated_payload["eventId"],
        "referenceId": 1,
    }
    assert auth_service.validated_tokens == ["valid-token", "valid-token"]

    async with InMemoryCustomerSynchronizationUnitOfWork(store) as work:
        customer = await work.customers.get_customer(1)
        assert customer is not None
        assert customer.company.name == "ACME Italia SRL"
        assert customer.company.website is None
        assert customer.company.primary_phone == ""
        assert customer.communication_preferences.newsletter is False
        assert customer.commercial.payment_days == 0
        assert customer.notes.items == ()
        assert await work.resource_versions.get_resource_version(1) == 2
        assert await work.processed_events.get_processed_result(
            convert_customer_event(_EVENT_ADAPTER.validate_python(updated_payload))
        ) is not None


@pytest.mark.anyio
@pytest.mark.parametrize("authorization", [None, "Bearer wrong-token"])
async def test_missing_or_invalid_token_cannot_create_a_customer(
    authorization: str | None,
    store: InMemoryCustomerSynchronizationStore,
) -> None:
    auth_service = _authenticate_as(Role.ADMIN)
    payload = _create_payload()
    headers = {"Authorization": authorization} if authorization else {}

    async with _client() as client:
        response = await client.post(_URL, json=payload, headers=headers)

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid credentials"}
    assert auth_service.validated_tokens == (
        [] if authorization is None else ["wrong-token"]
    )
    async with InMemoryCustomerSynchronizationUnitOfWork(store) as work:
        assert await work.customers.get_customer(1) is None
        assert await work.processed_events.get_processed_result(
            convert_customer_event(_EVENT_ADAPTER.validate_python(payload))
        ) is None


@pytest.mark.anyio
@pytest.mark.parametrize("role", [Role.BUYER, Role.CUSTOMER])
async def test_non_admin_cannot_create_a_customer(
    role: Role,
    store: InMemoryCustomerSynchronizationStore,
) -> None:
    auth_service = _authenticate_as(role)
    payload = _create_payload()

    async with _client() as client:
        response = await client.post(_URL, json=payload, headers=_HEADERS)

    assert response.status_code == 403
    assert response.json() == {"detail": "Forbidden"}
    assert auth_service.validated_tokens == ["valid-token"]
    async with InMemoryCustomerSynchronizationUnitOfWork(store) as work:
        assert await work.customers.get_customer(1) is None
        assert await work.processed_events.get_processed_result(
            convert_customer_event(_EVENT_ADAPTER.validate_python(payload))
        ) is None


@pytest.mark.anyio
async def test_non_admin_cannot_update_an_existing_customer(
    store: InMemoryCustomerSynchronizationStore,
) -> None:
    _authenticate_as(Role.ADMIN)
    update_payload = _update_payload(1)

    async with _client() as client:
        created = await client.post(
            _URL, json=_create_payload(), headers=_HEADERS
        )
        _authenticate_as(Role.BUYER)
        denied = await client.post(_URL, json=update_payload, headers=_HEADERS)

    assert created.status_code == 200
    assert denied.status_code == 403
    async with InMemoryCustomerSynchronizationUnitOfWork(store) as work:
        customer = await work.customers.get_customer(1)
        assert customer is not None
        assert customer.company.website == _create_payload()["data"]["company"][
            "website"
        ]
        assert await work.resource_versions.get_resource_version(1) == 1
        assert await work.processed_events.get_processed_result(
            convert_customer_event(_EVENT_ADAPTER.validate_python(update_payload))
        ) is None


@pytest.mark.anyio
async def test_admin_gets_not_found_for_an_unknown_customer(
    store: InMemoryCustomerSynchronizationStore,
) -> None:
    _authenticate_as(Role.ADMIN)
    payload = _update_payload(42)

    async with _client() as client:
        response = await client.post(_URL, json=payload, headers=_HEADERS)

    assert response.status_code == 404
    async with InMemoryCustomerSynchronizationUnitOfWork(store) as work:
        assert await work.customers.get_customer(42) is None
        assert await work.processed_events.get_processed_result(
            convert_customer_event(_EVENT_ADAPTER.validate_python(payload))
        ) is None


@pytest.mark.anyio
async def test_admin_gets_conflict_for_reused_event_id(
    store: InMemoryCustomerSynchronizationStore,
) -> None:
    _authenticate_as(Role.ADMIN)
    original = _create_payload()
    changed = _create_payload()
    changed["data"]["company"]["name"] = "Other name"

    async with _client() as client:
        created = await client.post(_URL, json=original, headers=_HEADERS)
        conflict = await client.post(_URL, json=changed, headers=_HEADERS)

    assert created.status_code == 200
    assert conflict.status_code == 409
    async with InMemoryCustomerSynchronizationUnitOfWork(store) as work:
        customer = await work.customers.get_customer(1)
        assert customer is not None
        assert customer.company.name == "ACME Italia SRL"
        assert await work.customers.get_customer(2) is None


@pytest.mark.anyio
async def test_invalid_create_payload_returns_validation_error(
    store: InMemoryCustomerSynchronizationStore,
) -> None:
    _authenticate_as(Role.ADMIN)
    payload = _create_payload()
    del payload["data"]["company"]["name"]

    async with _client() as client:
        response = await client.post(_URL, json=payload, headers=_HEADERS)

    assert response.status_code == 422
    async with InMemoryCustomerSynchronizationUnitOfWork(store) as work:
        assert await work.customers.get_customer(1) is None


@pytest.mark.anyio
async def test_persistence_error_returns_service_unavailable(
    store: InMemoryCustomerSynchronizationStore,
) -> None:
    _authenticate_as(Role.ADMIN)

    class FailingService:
        async def synchronize_customer(self, _event: object) -> None:
            raise DBException("Database is down")

    async def override_service() -> FailingService:
        return FailingService()

    app.dependency_overrides[
        integration_routes.get_customer_synchronization_service
    ] = override_service

    async with _client() as client:
        response = await client.post(_URL, json=_create_payload(), headers=_HEADERS)

    assert response.status_code == 503
    assert response.json() == {"detail": "Customer persistence is unavailable"}
    async with InMemoryCustomerSynchronizationUnitOfWork(store) as work:
        assert await work.customers.get_customer(1) is None


def test_openapi_describes_access_errors_and_temporary_storage() -> None:
    operation = app.openapi()["paths"][_URL]["post"]

    assert "in memory" in operation["description"]
    assert {"400", "401", "403", "404", "409", "422", "503"} <= set(
        operation["responses"]
    )
