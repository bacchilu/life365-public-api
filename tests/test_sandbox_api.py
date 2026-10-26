"""HTTP isolation checks without any real database or external HTTP calls."""

from collections.abc import Iterator
from typing import Any, ClassVar

import httpx
import pytest

import app.api.dependencies as production_dependencies
import app.api.sandbox.services as sandbox_services
from app.api.application import create_api_application
from app.api.customers import routes as customer_routes
from app.api.dependencies import get_auth_service
from app.api.sandbox import create_sandbox_application
from app.api.sandbox.settings import SandboxConfigurationError, SandboxSettings
from app.application.domain import Customer, PrincipalIdentity, PrincipalType, Role
from app.application.exceptions import AuthenticationException, DBException
from app.application.ports import CredentialsGateway
from app.application.services.auth_service import AuthService
from app.infrastructure.auth import PyJWTTokenCodec
from app.infrastructure.data_mapper.auth import InMemoryTokenSessionDataMapper
from app.infrastructure.life365_portal_api import Life365PortalAPI

_CONNECTION = "host=127.0.0.1 port=55432 dbname=life365_sandbox user=sandbox_user password=local-test"


class _Credentials(CredentialsGateway):
    connections: ClassVar[list[str]] = []

    def __init__(self, connection: str) -> None:
        self.connections.append(connection)

    async def authenticate_internal_user(
        self, username: str, password: str
    ) -> PrincipalIdentity:
        if password != "test-password" or username not in ("admin", "buyer"):
            raise AuthenticationException("Invalid credentials")
        return PrincipalIdentity(
            id=1,
            username=username,
            role=Role.ADMIN if username == "admin" else Role.BUYER,
            principal_type=PrincipalType.USER,
        )

    async def authenticate_customer(
        self, username: str, password: str
    ) -> PrincipalIdentity:
        if password != "test-password":
            raise AuthenticationException("Invalid credentials")
        return PrincipalIdentity(
            id=2,
            username=username,
            role=Role.CUSTOMER,
            principal_type=PrincipalType.CUSTOMER,
        )


class _Customers:
    def __init__(self, login: str) -> None:
        self.login = login

    async def get_customers(self, limit: int = 100, offset: int = 0) -> list[Customer]:
        return [Customer(id=1, login=self.login, email="sample@example.com")]


@pytest.fixture
def apps(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[Any, Any, AuthService]]:
    _Credentials.connections = []
    monkeypatch.setattr(sandbox_services, "CredentialsDataMapper", _Credentials)
    normal = create_api_application("Existing API")
    sandbox = create_sandbox_application(
        SandboxSettings(
            _CONNECTION,
            "sandbox-jwt-secret-for-tests-32-bytes",
            b"sandbox-event-secret-for-tests-32-bytes",
        )
    )
    normal.mount("/sandbox", sandbox)
    normal_auth = AuthService(
        _Credentials("existing-database"),
        InMemoryTokenSessionDataMapper(),
        PyJWTTokenCodec("production-jwt-secret-for-tests-32-bytes"),
    )

    async def auth() -> AuthService:
        return normal_auth

    normal.dependency_overrides[get_auth_service] = auth
    monkeypatch.setattr(customer_routes, "customer_service", _Customers("existing"))
    sandbox.state.sandbox_services.customers = _Customers("sandbox")
    yield normal, sandbox, normal_auth


def _client(app: Any, *, root_path: str = "") -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(
            app=app, root_path=root_path, client=("127.0.0.1", 1234)
        ),
        base_url="http://testserver",
    )


async def _token(
    client: httpx.AsyncClient,
    prefix: str,
    username: str = "admin",
    principal_type: str = "user",
) -> str:
    response = await client.post(
        f"{prefix}/auth/login",
        json={
            "username": username,
            "password": "test-password",
            "principal_type": principal_type,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


@pytest.mark.anyio
async def test_tokens_sessions_and_dependency_overrides_are_separate(
    apps: tuple,
) -> None:
    normal, sandbox, _ = apps
    previous_singleton = production_dependencies._auth_service
    original_override = normal.dependency_overrides[get_auth_service]
    async with _client(normal) as client:
        existing_token = await _token(client, "")
        sandbox_token = await _token(client, "/sandbox")
        for prefix, token, expected in [
            ("", existing_token, "existing"),
            ("/sandbox", sandbox_token, "sandbox"),
        ]:
            response = await client.get(
                prefix + "/customers", headers={"Authorization": f"Bearer {token}"}
            )
            assert response.status_code == 200
            assert response.json()[0]["login"] == expected
        for prefix, token in [("", sandbox_token), ("/sandbox", existing_token)]:
            response = await client.get(
                prefix + "/customers", headers={"Authorization": f"Bearer {token}"}
            )
            assert response.status_code == 401
        response = await client.post(
            "/sandbox/auth/logout", headers={"Authorization": f"Bearer {sandbox_token}"}
        )
        assert response.status_code == 200
        assert (
            await client.get(
                "/sandbox/customers",
                headers={"Authorization": f"Bearer {sandbox_token}"},
            )
        ).status_code == 401
        assert (
            await client.get(
                "/customers", headers={"Authorization": f"Bearer {existing_token}"}
            )
        ).status_code == 200
    assert normal.dependency_overrides[get_auth_service] is original_override
    assert sandbox.dependency_overrides[get_auth_service] is not original_override
    assert production_dependencies._auth_service is previous_singleton


@pytest.mark.anyio
async def test_all_sandbox_mappers_use_only_the_explicit_connection(
    apps: tuple,
) -> None:
    _, sandbox, _ = apps
    services = sandbox.state.sandbox_services
    for service in (services.orders, services.products, services.health):
        assert service._data_mapper._connection_string == _CONNECTION
    synchronization = services.customer_synchronization("127.0.0.1")
    assert synchronization._unit_of_work._connection_string == _CONNECTION
    assert _Credentials.connections == [_CONNECTION, "existing-database"]


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("username", "principal_type"), [("buyer", "user"), ("customer", "customer")]
)
async def test_sandbox_keeps_admin_authorization(
    apps: tuple, username: str, principal_type: str
) -> None:
    async with _client(apps[0]) as client:
        token = await _token(client, "/sandbox", username, principal_type)
        response = await client.get(
            "/sandbox/customers", headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 403


@pytest.mark.anyio
async def test_real_external_gateway_is_never_called(
    apps: tuple, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def forbidden(*args: Any, **kwargs: Any) -> None:
        pytest.fail("Sandbox attempted real external business HTTP")

    monkeypatch.setattr(Life365PortalAPI, "recommend_products", forbidden)
    async with _client(apps[0]) as client:
        assert (
            await client.get("/sandbox/products/recommend?order_id=1")
        ).status_code == 401
        token = await _token(client, "/sandbox")
        response = await client.get(
            "/sandbox/products/recommend?order_id=1",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 501
        assert "no external request" in response.json()["detail"]


@pytest.mark.anyio
@pytest.mark.parametrize("prefix", ["", "/public-api", "/api/public/v1"])
async def test_mounted_swagger_and_openapi_honor_proxy_root_path(
    apps: tuple, prefix: str
) -> None:
    async with _client(apps[0], root_path=prefix) as client:
        docs = await client.get(prefix + "/sandbox/docs")
        assert docs.status_code == 200
        assert prefix + "/sandbox/openapi.json" in docs.text
        response = await client.get(prefix + "/sandbox/openapi.json")
        assert response.status_code == 200
        schema = response.json()
        assert schema["info"]["title"] == "Life365 Public API Sandbox"
        assert {"url": prefix + "/sandbox"} in schema["servers"]
        assert {
            "/auth/login",
            "/auth/logout",
            "/customers",
            "/orders",
            "/products",
            "/integrations/salesforce/events",
        } <= set(schema["paths"])
        for name in ("CustomerCreatedEventRequest", "CustomerUpdatedEventRequest"):
            assert (
                "resourceVersion"
                not in schema["components"]["schemas"][name]["properties"]
            )
            assert (
                schema["components"]["schemas"][name]["additionalProperties"] is False
            )


@pytest.mark.anyio
async def test_unconfigured_sandbox_does_not_use_existing_services(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unavailable() -> SandboxSettings:
        raise SandboxConfigurationError("Missing sandbox settings")

    monkeypatch.setattr(SandboxSettings, "load", unavailable)
    normal = create_api_application("Existing API")
    normal.mount("/sandbox", create_sandbox_application())
    async with _client(normal) as client:
        assert (await client.get("/sandbox/docs")).status_code == 200
        assert (await client.get("/sandbox/health")).status_code == 503
        response = await client.post(
            "/sandbox/auth/login",
            json={"username": "admin", "password": "secret", "principal_type": "user"},
        )
        assert response.status_code == 503
        assert "secret" not in response.text


@pytest.mark.anyio
async def test_sandbox_persistence_errors_do_not_fall_back(
    apps: tuple, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def failed(*args: Any, **kwargs: Any) -> list[Customer]:
        raise DBException("Unavailable")

    monkeypatch.setattr(
        apps[1].state.sandbox_services.customers, "get_customers", failed
    )
    async with _client(apps[0]) as client:
        token = await _token(client, "/sandbox")
        response = await client.get(
            "/sandbox/customers", headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 503


def test_jwt_issuer_and_audience_are_required_even_with_the_same_signing_key() -> None:
    key = "shared-only-for-this-isolation-test-32-bytes"
    normal = PyJWTTokenCodec(key)
    sandbox = PyJWTTokenCodec(
        key, issuer="life365-sandbox", audience="life365-public-api:sandbox"
    )
    normal_token = normal.encode({"sub": "1"})
    sandbox_token = sandbox.encode({"sub": "1"})
    assert normal.decode(normal_token) == {"sub": "1"}
    assert sandbox.decode(sandbox_token)["iss"] == "life365-sandbox"
    for codec, token in ((normal, sandbox_token), (sandbox, normal_token)):
        with pytest.raises(AuthenticationException):
            codec.decode(token)
    for issuer, audience in (
        ("other", "life365-public-api:sandbox"),
        ("life365-sandbox", "other"),
    ):
        with pytest.raises(AuthenticationException):
            sandbox.decode(
                PyJWTTokenCodec(key, issuer=issuer, audience=audience).encode(
                    {"sub": "1"}
                )
            )
