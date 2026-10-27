"""Test both mounted outbound routes without database or network access."""

from collections.abc import Iterator
from dataclasses import replace

import httpx
import pytest
from fastapi import FastAPI

from app.api.application import create_api_application
from app.api.dependencies import get_auth_service
from app.api.integrations import export_dependencies as composition
from app.api.integrations.export_dependencies import get_customer_export_service
from app.api.sandbox import create_sandbox_application
from app.api.sandbox.services import SandboxServices
from app.api.sandbox.settings import SandboxSettings
from app.application.domain import (
    AuthenticatedUser,
    PrincipalType,
    Role,
    resolve_permissions,
    resolve_product_access_policy,
)
from app.application.exceptions import (
    AuthenticationException,
    CustomerNotFoundException,
    DBException,
    InvalidCustomerDataException,
    SalesforceConfigurationException,
    SalesforceRequestException,
    SalesforceTimeoutException,
)
from app.application.services.customer_export_service import CustomerExportService
from app.infrastructure.data_mapper.customer_export import (
    PostgreSQLCustomerExportDataMapper,
)
from app.infrastructure.salesforce import SalesforceCustomerAPI, SalesforceSettings
from tests.test_customer_export_service import Gateway, Reader, customer_data

_PATH = "/integrations/salesforce/customers/42"
_HEADERS = {"Authorization": "Bearer test-token"}


class Auth:
    role: Role = Role.ADMIN

    async def validate_token(self, token: str | None) -> AuthenticatedUser:
        if token != "test-token":
            raise AuthenticationException("Invalid credentials")
        return AuthenticatedUser(
            id=1,
            username="test",
            role=self.role,
            principal_type=PrincipalType.USER,
            token_id="test",
            permissions=resolve_permissions(self.role),
            product_access=resolve_product_access_policy(self.role, user_id=1),
        )


@pytest.fixture
def setup() -> Iterator[tuple[FastAPI, Auth, Reader, Reader, Gateway]]:
    root = create_api_application("Existing API")
    sandbox = create_sandbox_application(
        SandboxSettings(
            "sandbox-test-only",
            "sandbox-jwt-secret-for-tests-32-bytes",
            b"sandbox-event-secret-for-tests-32-bytes",
        )
    )
    root.mount("/sandbox", sandbox)
    auth = Auth()
    data = customer_data()
    regular = Reader(data)
    isolated = Reader(
        replace(data, credentials=replace(data.credentials, login="sandbox-only"))
    )
    gateway = Gateway()

    async def authentication() -> Auth:
        return auth

    async def normal_service() -> CustomerExportService:
        return CustomerExportService(regular, gateway)

    async def sandbox_service() -> CustomerExportService:
        return CustomerExportService(isolated, gateway)

    root.dependency_overrides[get_auth_service] = authentication
    sandbox.dependency_overrides[get_auth_service] = authentication
    root.dependency_overrides[get_customer_export_service] = normal_service
    sandbox.dependency_overrides[get_customer_export_service] = sandbox_service
    yield root, auth, regular, isolated, gateway


def _client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    )


@pytest.mark.anyio
@pytest.mark.parametrize("prefix", ["", "/sandbox"])
async def test_post_and_put_send_full_current_data(
    setup: tuple[FastAPI, Auth, Reader, Reader, Gateway], prefix: str
) -> None:
    root, _, regular, isolated, gateway = setup
    async with _client(root) as client:
        created = await client.post(prefix + _PATH, headers=_HEADERS)
        updated = await client.put(prefix + _PATH, headers=_HEADERS)
    assert created.status_code == 201, created.text
    assert updated.status_code == 200, updated.text
    assert set(created.json()) == {"success", "eventId", "referenceId", "accountId"}
    assert created.json()["referenceId"] == updated.json()["referenceId"] == 42
    assert created.json()["eventId"] != updated.json()["eventId"]
    assert [event.event_type for event in gateway.events] == [
        "customer.created",
        "customer.updated",
    ]
    expected = isolated.customer if prefix else regular.customer
    assert all(event.data is expected for event in gateway.events)
    assert (regular.calls, isolated.calls) == (
        ([], [42, 42]) if prefix else ([42, 42], [])
    )


@pytest.mark.anyio
@pytest.mark.parametrize("prefix", ["", "/sandbox"])
@pytest.mark.parametrize("role", [Role.BUYER, Role.CUSTOMER])
async def test_non_admin_cannot_read_or_export(
    setup: tuple[FastAPI, Auth, Reader, Reader, Gateway], prefix: str, role: Role
) -> None:
    root, auth, regular, isolated, gateway = setup
    auth.role = role
    async with _client(root) as client:
        assert (await client.post(prefix + _PATH, headers=_HEADERS)).status_code == 403
        assert (await client.put(prefix + _PATH, headers=_HEADERS)).status_code == 403
    assert regular.calls == isolated.calls == [] and gateway.events == []


@pytest.mark.anyio
async def test_authentication_body_and_path_validation(
    setup: tuple[FastAPI, Auth, Reader, Reader, Gateway],
) -> None:
    root, _, regular, isolated, gateway = setup
    async with _client(root) as client:
        for prefix in ("", "/sandbox"):
            assert (await client.post(prefix + _PATH)).status_code == 401
            assert (
                await client.put(
                    prefix + _PATH, headers={"Authorization": "Bearer invalid"}
                )
            ).status_code == 401
            for identifier in ("0", "-1", "invalid"):
                assert (
                    await client.put(
                        prefix + _PATH.replace("42", identifier), headers=_HEADERS
                    )
                ).status_code == 422
            assert (
                await client.put(
                    prefix + _PATH, headers=_HEADERS, json={"resourceVersion": 1}
                )
            ).status_code == 422
    assert regular.calls == isolated.calls == [] and gateway.events == []


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("error", "status"),
    [
        (CustomerNotFoundException("Customer missing"), 404),
        (InvalidCustomerDataException("Incomplete data"), 422),
        (DBException("Sensitive DB details"), 503),
        (SalesforceConfigurationException("Missing Salesforce configuration"), 503),
        (
            SalesforceRequestException(
                "Salesforce rejected the event", remote_status=409
            ),
            409,
        ),
        (
            SalesforceRequestException(
                "Salesforce rejected the event", remote_status=400
            ),
            502,
        ),
        (SalesforceTimeoutException("Remote outcome is unknown"), 504),
    ],
)
async def test_errors_are_translated_only_by_api(
    setup: tuple[FastAPI, Auth, Reader, Reader, Gateway], error: Exception, status: int
) -> None:
    root, _, regular, _, gateway = setup
    if isinstance(
        error, (CustomerNotFoundException, InvalidCustomerDataException, DBException)
    ):
        regular.failure = error
    else:
        gateway.failure = error
    async with _client(root) as client:
        response = await client.put(_PATH, headers=_HEADERS)
    assert response.status_code == status
    assert "Sensitive" not in response.text


@pytest.mark.anyio
async def test_openapi_describes_no_body_and_real_sandbox_exports(
    setup: tuple[FastAPI, Auth, Reader, Reader, Gateway],
) -> None:
    async with _client(setup[0]) as client:
        for prefix in ("", "/sandbox"):
            response = await client.get(prefix + "/openapi.json")
            schema = response.json()
            operations = schema["paths"][
                "/integrations/salesforce/customers/{customer_id}"
            ]
            assert set(operations) == {"post", "put"}
            for operation in operations.values():
                assert "requestBody" not in operation
                assert "same real Salesforce API" in operation["description"]
                assert {"401", "403", "404", "409", "422", "502", "503", "504"} <= set(
                    operation["responses"]
                )


@pytest.mark.anyio
async def test_composition_uses_different_readers_and_the_same_real_adapter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway = SalesforceCustomerAPI(
        SalesforceSettings(
            "https://unit.my.salesforce.com/services/oauth2/token",
            "https://unit.my.salesforce.com/services/apexrest/customer/sync/",
            "test-id",
            "test-secret",
        )
    )
    monkeypatch.setattr(composition, "_salesforce_gateway", gateway)
    monkeypatch.setattr(composition, "DATABASE_URL", "normal-database-only")
    normal = await composition.get_customer_export_service(
        await Auth().validate_token("test-token")
    )
    sandbox = SandboxServices(
        SandboxSettings(
            "sandbox-database-only", "sandbox-key", b"sandbox-fingerprint-key"
        )
    ).customer_export()
    normal_reader, sandbox_reader = normal._reader, sandbox._reader
    assert isinstance(normal_reader, PostgreSQLCustomerExportDataMapper)
    assert isinstance(sandbox_reader, PostgreSQLCustomerExportDataMapper)
    assert normal_reader._connection_string == "normal-database-only"
    assert sandbox_reader._connection_string == "sandbox-database-only"
    assert normal._salesforce_gateway is sandbox._salesforce_gateway is gateway
