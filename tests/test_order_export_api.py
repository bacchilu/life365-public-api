"""Reuse real routes in normal and sandbox apps, with no real remote calls."""

from collections.abc import Iterator
from dataclasses import replace

import httpx
import pytest
from fastapi import FastAPI

from app.api.application import create_api_application
from app.api.dependencies import get_auth_service
from app.api.integrations import order_export_dependencies as composition
from app.api.integrations.order_export_dependencies import get_order_export_service
from app.api.sandbox import create_sandbox_application
from app.api.sandbox.services import SandboxServices
from app.api.sandbox.settings import SandboxSettings
from app.application.domain import Role
from app.application.exceptions import (
    DBException,
    InvalidOrderDataException,
    OrderNotFoundException,
    SalesforceConfigurationException,
    SalesforceRequestException,
    SalesforceTimeoutException,
)
from app.application.services.order_export_service import OrderExportService
from app.infrastructure.data_mapper.order_export import PostgreSQLOrderExportDataMapper
from app.infrastructure.salesforce import SalesforceOrderAPI, SalesforceSettings
from tests.test_order_export_service import Gateway, Reader, order_data
from tests.test_product_export_api import Auth

_PATH = "/integrations/salesforce/orders/1001"
_METHODS = ("POST", "PUT", "DELETE")
Setup = tuple[FastAPI, Auth, Auth, Reader, Reader, Gateway]


@pytest.fixture
def setup() -> Iterator[Setup]:
    root = create_api_application("Normal API")
    sandbox = create_sandbox_application(
        SandboxSettings("sandbox-test-only", "sandbox-key", b"sandbox-fingerprint")
    )
    root.mount("/sandbox", sandbox)
    normal_auth, sandbox_auth = Auth("normal-token"), Auth("sandbox-token")
    normal, isolated = (
        Reader(order_data()),
        Reader(replace(order_data(), status="DELIVERED")),
    )
    gateway = Gateway()

    async def auth_normal() -> Auth:
        return normal_auth

    async def auth_sandbox() -> Auth:
        return sandbox_auth

    async def service_normal() -> OrderExportService:
        return OrderExportService(normal, gateway)

    async def service_sandbox() -> OrderExportService:
        return OrderExportService(isolated, gateway)

    root.dependency_overrides[get_auth_service] = auth_normal
    sandbox.dependency_overrides[get_auth_service] = auth_sandbox
    root.dependency_overrides[get_order_export_service] = service_normal
    sandbox.dependency_overrides[get_order_export_service] = service_sandbox
    yield root, normal_auth, sandbox_auth, normal, isolated, gateway


def client(app: FastAPI, root_path: str = "") -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, root_path=root_path),
        base_url="http://testserver",
    )


def headers(prefix: str) -> dict[str, str]:
    return {
        "Authorization": "Bearer sandbox-token" if prefix else "Bearer normal-token"
    }


@pytest.mark.anyio
@pytest.mark.parametrize("prefix", ["", "/sandbox"])
async def test_all_methods_use_selected_reader(setup: Setup, prefix: str) -> None:
    root, _, _, normal, isolated, gateway = setup
    async with client(root) as http:
        responses = [
            await http.request(method, prefix + _PATH, headers=headers(prefix))
            for method in _METHODS
        ]
    assert [r.status_code for r in responses] == [201, 200, 200]
    assert all(
        set(r.json()) == {"success", "eventId", "referenceId", "recordId"}
        for r in responses
    )
    assert len({r.json()["eventId"] for r in responses}) == 3
    selected, untouched = (isolated, normal) if prefix else (normal, isolated)
    assert selected.calls == [1001, 1001] and selected.existence_calls == [1001]
    assert untouched.calls == untouched.existence_calls == []
    assert [e.event_type for e in gateway.events] == [
        "order.created",
        "order.updated",
        "order.deleted",
    ]
    assert gateway.events[0].data is gateway.events[1].data is selected.data
    assert gateway.events[2].data is None


@pytest.mark.anyio
@pytest.mark.parametrize("prefix", ["", "/sandbox"])
@pytest.mark.parametrize("role", [Role.ADMIN, Role.BUYER, Role.CUSTOMER])
async def test_integration_rule_before_any_read_or_send(
    setup: Setup, prefix: str, role: Role
) -> None:
    root, normal_auth, sandbox_auth, normal, isolated, gateway = setup
    (sandbox_auth if prefix else normal_auth).role = role
    async with client(root) as http:
        for method in _METHODS:
            assert (
                await http.request(method, prefix + _PATH, headers=headers(prefix))
            ).status_code == 403
    assert normal.calls == isolated.calls == gateway.events == []


@pytest.mark.anyio
async def test_missing_or_wrong_environment_token_and_body_guards(setup: Setup) -> None:
    root, _, _, normal, isolated, gateway = setup
    async with client(root) as http:
        for prefix in ("", "/sandbox"):
            for method in _METHODS:
                assert (await http.request(method, prefix + _PATH)).status_code == 401
                assert (
                    await http.request(
                        method,
                        prefix + _PATH,
                        headers=headers("" if prefix else "/sandbox"),
                    )
                ).status_code == 401
                assert (
                    await http.request(
                        method, prefix + _PATH, headers=headers(prefix), json={}
                    )
                ).status_code == 422
                for identifier in ("0", "-1", "invalid"):
                    assert (
                        await http.request(
                            method,
                            prefix + _PATH.replace("1001", identifier),
                            headers=headers(prefix),
                        )
                    ).status_code == 422
    assert normal.calls == isolated.calls == gateway.events == []


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("failure", "code"),
    [
        (OrderNotFoundException("Missing"), 404),
        (InvalidOrderDataException("Invalid source"), 422),
        (DBException("secret DB details"), 503),
        (SalesforceConfigurationException("Invalid settings"), 503),
        (
            SalesforceRequestException("Missing upstream customer", remote_status=404),
            404,
        ),
        (SalesforceRequestException("Conflict", remote_status=409), 409),
        (SalesforceRequestException("Rejected", remote_status=400), 502),
        (SalesforceTimeoutException("Remote outcome unknown"), 504),
    ],
)
async def test_error_translation(setup: Setup, failure: Exception, code: int) -> None:
    root, _, _, reader, _, gateway = setup
    if isinstance(
        failure, (OrderNotFoundException, InvalidOrderDataException, DBException)
    ):
        reader.failure = failure
    else:
        gateway.failure = failure
    async with client(root) as http:
        response = await http.post(_PATH, headers=headers(""))
    assert response.status_code == code
    assert "secret" not in response.text


@pytest.mark.anyio
async def test_normal_and_sandbox_composition_have_separate_readers_shared_remote(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    remote = SalesforceOrderAPI(
        SalesforceSettings(
            "https://unit.my.salesforce.com/token",
            "https://unit.my.salesforce.com/customer",
            "test",
            "secret",
        )
    )
    monkeypatch.setattr(composition, "_salesforce_order_gateway", remote)
    monkeypatch.setattr(composition, "DATABASE_URL", "normal-db-only")
    normal = await composition.get_order_export_service(
        await Auth("normal-token").validate_token("normal-token")
    )
    services = SandboxServices(
        SandboxSettings("sandbox-db-only", "test-key", b"test-fingerprint")
    )
    exported = services.order_export()
    assert isinstance(exported._reader, PostgreSQLOrderExportDataMapper)
    assert exported._reader._connection_string == "sandbox-db-only"
    assert isinstance(normal._reader, PostgreSQLOrderExportDataMapper)
    assert normal._reader._connection_string == "normal-db-only"
    assert exported._salesforce_gateway is normal._salesforce_gateway is remote


@pytest.mark.anyio
async def test_swagger_paths_schemas_and_reverse_proxy_root(setup: Setup) -> None:
    root = setup[0]
    async with client(root, "/public-api") as http:
        for prefix, server in [
            ("", "/public-api"),
            ("/sandbox", "/public-api/sandbox"),
        ]:
            response = await http.get("/public-api" + prefix + "/openapi.json")
            assert response.status_code == 200
            schema = response.json()
            path = schema["paths"]["/integrations/salesforce/orders/{order_id}"]
            assert set(_METHODS) == {m.upper() for m in path}
            assert all("requestBody" not in operation for operation in path.values())
            for operation in path.values():
                assert "Integration role required" in operation["description"]
                assert (
                    "Integration role required"
                    in operation["responses"]["403"]["description"]
                )
            assert schema["servers"][0]["url"] == server
            assert set(
                schema["components"]["schemas"]["OrderExportResponse"]["properties"]
            ) == {"success", "eventId", "referenceId", "recordId"}
