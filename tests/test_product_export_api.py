"""Exercise all three HTTP methods in independently configured applications."""

from collections.abc import Iterator
from dataclasses import replace

import httpx
import pytest
from fastapi import FastAPI

from app.api.application import create_api_application
from app.api.dependencies import get_auth_service
from app.api.integrations import product_export_dependencies as composition
from app.api.integrations.product_export_dependencies import get_product_export_service
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
    DBException,
    InvalidProductDataException,
    ProductNotFoundException,
    SalesforceConfigurationException,
    SalesforceRequestException,
    SalesforceTimeoutException,
)
from app.application.services.product_export_service import ProductExportService
from app.infrastructure.data_mapper.product_export import (
    PostgreSQLProductExportDataMapper,
)
from app.infrastructure.salesforce import SalesforceProductAPI, SalesforceSettings
from tests.test_product_export_service import Gateway, Reader, product_data

_PATH = "/integrations/salesforce/products/101"
_METHODS = ("POST", "PUT", "DELETE")


class Auth:
    role: Role = Role.INTEGRATION

    def __init__(self, token: str) -> None:
        self.token = token

    async def validate_token(self, token: str | None) -> AuthenticatedUser:
        if token != self.token:
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


Setup = tuple[FastAPI, Auth, Auth, Reader, Reader, Gateway]


@pytest.fixture
def setup() -> Iterator[Setup]:
    root = create_api_application("Existing API")
    sandbox = create_sandbox_application(
        SandboxSettings("sandbox-test-only", "sandbox-key", b"sandbox-fingerprint")
    )
    root.mount("/sandbox", sandbox)
    normal_auth, sandbox_auth = Auth("normal-token"), Auth("sandbox-token")
    normal, isolated = (
        Reader(product_data()),
        Reader(replace(product_data(), sku="sandbox-only")),
    )
    gateway = Gateway()

    async def auth_normal() -> Auth:
        return normal_auth

    async def auth_sandbox() -> Auth:
        return sandbox_auth

    async def service_normal() -> ProductExportService:
        return ProductExportService(normal, gateway)

    async def service_sandbox() -> ProductExportService:
        return ProductExportService(isolated, gateway)

    root.dependency_overrides[get_auth_service] = auth_normal
    sandbox.dependency_overrides[get_auth_service] = auth_sandbox
    root.dependency_overrides[get_product_export_service] = service_normal
    sandbox.dependency_overrides[get_product_export_service] = service_sandbox
    yield root, normal_auth, sandbox_auth, normal, isolated, gateway


def _client(app: FastAPI, root_path: str = "") -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, root_path=root_path),
        base_url="http://testserver",
    )


def _headers(prefix: str) -> dict[str, str]:
    return {
        "Authorization": "Bearer sandbox-token" if prefix else "Bearer normal-token"
    }


@pytest.mark.anyio
@pytest.mark.parametrize("prefix", ["", "/sandbox"])
async def test_create_update_delete_read_only_the_selected_database(
    setup: Setup, prefix: str
) -> None:
    root, _, _, normal, isolated, gateway = setup
    async with _client(root) as client:
        responses = [
            await client.request(method, prefix + _PATH, headers=_headers(prefix))
            for method in _METHODS
        ]
    assert [response.status_code for response in responses] == [201, 200, 200]
    assert all(
        set(response.json()) == {"success", "eventId", "referenceId", "recordId"}
        for response in responses
    )
    assert len({response.json()["eventId"] for response in responses}) == 3
    assert [event.event_type for event in gateway.events] == [
        "product.created",
        "product.updated",
        "product.deleted",
    ]
    selected, untouched = (isolated, normal) if prefix else (normal, isolated)
    assert selected.calls == [101, 101] and selected.existence_calls == [101]
    assert untouched.calls == untouched.existence_calls == []
    assert (
        gateway.events[0].data is selected.data
        and gateway.events[1].data is selected.data
    )
    assert gateway.events[2].data is None


@pytest.mark.anyio
@pytest.mark.parametrize("prefix", ["", "/sandbox"])
@pytest.mark.parametrize("role", [Role.ADMIN, Role.BUYER, Role.CUSTOMER])
async def test_non_integration_user_cannot_read_or_send(
    setup: Setup, prefix: str, role: Role
) -> None:
    root, normal_auth, sandbox_auth, normal, isolated, gateway = setup
    (sandbox_auth if prefix else normal_auth).role = role
    async with _client(root) as client:
        for method in _METHODS:
            assert (
                await client.request(method, prefix + _PATH, headers=_headers(prefix))
            ).status_code == 403
    assert (
        normal.calls
        == isolated.calls
        == normal.existence_calls
        == isolated.existence_calls
        == gateway.events
        == []
    )


@pytest.mark.anyio
async def test_tokens_body_and_path_guards(setup: Setup) -> None:
    root, _, _, normal, isolated, gateway = setup
    async with _client(root) as client:
        for prefix in ("", "/sandbox"):
            for method in _METHODS:
                assert (await client.request(method, prefix + _PATH)).status_code == 401
                wrong_headers = _headers("" if prefix else "/sandbox")
                assert (
                    await client.request(method, prefix + _PATH, headers=wrong_headers)
                ).status_code == 401
                for identifier in ("0", "-1", "invalid"):
                    assert (
                        await client.request(
                            method,
                            prefix + _PATH.replace("101", identifier),
                            headers=_headers(prefix),
                        )
                    ).status_code == 422
                assert (
                    await client.request(
                        method, prefix + _PATH, headers=_headers(prefix), json={}
                    )
                ).status_code == 422
    assert (
        normal.calls
        == isolated.calls
        == normal.existence_calls
        == isolated.existence_calls
        == gateway.events
        == []
    )


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("failure", "status"),
    [
        (ProductNotFoundException("Missing"), 404),
        (InvalidProductDataException("Invalid category"), 422),
        (DBException("Sensitive database information"), 503),
        (SalesforceConfigurationException("Invalid settings"), 503),
        (SalesforceRequestException("Conflict", remote_status=409), 409),
        (SalesforceRequestException("Upstream rejected", remote_status=400), 502),
        (SalesforceTimeoutException("Remote outcome unknown"), 504),
    ],
)
async def test_error_translation(setup: Setup, failure: Exception, status: int) -> None:
    root, _, _, reader, _, gateway = setup
    if isinstance(
        failure, (ProductNotFoundException, InvalidProductDataException, DBException)
    ):
        reader.failure = failure
    else:
        gateway.failure = failure
    async with _client(root) as client:
        response = await client.put(_PATH, headers=_headers(""))
    assert response.status_code == status and "Sensitive" not in response.text


@pytest.mark.anyio
async def test_remote_missing_product_is_404_only_for_delete(setup: Setup) -> None:
    root, _, _, _, _, gateway = setup
    gateway.failure = SalesforceRequestException(
        "Remote product missing", remote_status=404
    )
    async with _client(root) as client:
        assert (await client.delete(_PATH, headers=_headers(""))).status_code == 404
        assert (await client.put(_PATH, headers=_headers(""))).status_code == 502


@pytest.mark.anyio
async def test_openapi_documents_all_methods_without_body_and_proxy_paths(
    setup: Setup,
) -> None:
    async with _client(setup[0], "/public-api") as client:
        for prefix in ("", "/sandbox"):
            schema = (await client.get("/public-api" + prefix + "/openapi.json")).json()
            assert {"url": "/public-api" + prefix} in schema["servers"]
            operations = schema["paths"][
                "/integrations/salesforce/products/{product_id}"
            ]
            assert set(operations) == {"post", "put", "delete"}
            for operation in operations.values():
                assert "Integration role" in operation["description"]
                assert (
                    "Integration role required"
                    in operation["responses"]["403"]["description"]
                )
                assert "requestBody" not in operation
                assert "same real Salesforce API" in operation["description"]
                assert {"401", "403", "404", "409", "422", "502", "503", "504"} <= set(
                    operation["responses"]
                )


@pytest.mark.anyio
async def test_composition_keeps_databases_separate_and_shares_real_gateway(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway = SalesforceProductAPI(
        SalesforceSettings(
            "https://unit.my.salesforce.com/services/oauth2/token",
            "https://unit.my.salesforce.com/services/apexrest/customer/sync/",
            "test-id",
            "test-secret",
        )
    )
    monkeypatch.setattr(composition, "_salesforce_product_gateway", gateway)
    monkeypatch.setattr(composition, "DATABASE_URL", "normal-database-only")
    normal = await composition.get_product_export_service(
        await Auth("normal-token").validate_token("normal-token")
    )
    sandbox = SandboxServices(
        SandboxSettings("sandbox-database-only", "sandbox-key", b"sandbox-fingerprint")
    ).product_export()
    assert isinstance(normal._reader, PostgreSQLProductExportDataMapper)
    assert isinstance(sandbox._reader, PostgreSQLProductExportDataMapper)
    assert normal._reader._connection_string == "normal-database-only"
    assert sandbox._reader._connection_string == "sandbox-database-only"
    assert normal._salesforce_gateway is sandbox._salesforce_gateway is gateway
