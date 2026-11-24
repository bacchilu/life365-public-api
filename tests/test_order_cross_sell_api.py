"""Exercise Flow 1 with the real route and adapter but no external network."""

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

import httpx
import pytest

from app.api.application import create_api_application
from app.api.dependencies import get_auth_service
from app.api.integrations import order_cross_sell_dependencies as composition
from app.api.sandbox import create_sandbox_application
from app.api.sandbox.settings import SandboxSettings
from app.application.domain import Role
from app.application.dtos.order_cross_sell import OrderCrossSellState
from app.application.exceptions import DBException, SalesforceConfigurationException
from app.infrastructure.data_mapper.order_cross_sell import (
    PostgreSQLOrderCrossSellDataMapper,
)
from app.infrastructure.salesforce import SalesforceSettings, auth
from app.infrastructure.salesforce.marketing_client import SalesforceMarketingAPI
from tests.test_product_export_api import Auth

_PATH = "/integrations/salesforce/orders/1001/marketing/cross-sell"
_BODY = {"related_product": ["117", "118", "123"]}
_RECEIPT = {
    "success": True,
    "flow": "recommended_products",
    "recordsCreated": 3,
    "recordIds": ["record-1", "record-2", "record-3"],
}


@dataclass
class Scenario:
    state: OrderCrossSellState | None = field(
        default_factory=lambda: OrderCrossSellState(4, "ACCEPTED", 25)
    )
    lookup_error: bool = False
    renew_token: bool = False
    timeout: bool = False
    remote_code: int = 201
    remote_body: dict[str, object] = field(default_factory=lambda: dict(_RECEIPT))
    reads: list[tuple[str, int]] = field(default_factory=list)
    requests: list[httpx.Request] = field(default_factory=list)
    normal_auth: Auth = field(default_factory=lambda: Auth("normal-token"))
    sandbox_auth: Auth = field(default_factory=lambda: Auth("sandbox-token"))

    def remote(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.path == "/token":
            assert b"grant_type=client_credentials" in request.content
            return httpx.Response(
                200, json={"access_token": f"fake-token-{len(self.requests)}"}
            )
        assert request.url.path == "/services/apexrest/marketing/products/"
        assert request.method == "POST"
        if (
            self.renew_token
            and request.headers["Authorization"] == "Bearer fake-token-1"
        ):
            return httpx.Response(401)
        if self.timeout:
            raise httpx.ReadTimeout("private remote detail")
        return httpx.Response(self.remote_code, json=self.remote_body)


@pytest.fixture
async def scenario(
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[tuple[httpx.AsyncClient, Scenario]]:
    case = Scenario()

    async def lookup(
        self: PostgreSQLOrderCrossSellDataMapper, order_id: int
    ) -> OrderCrossSellState | None:
        case.reads.append((self._connection_string, order_id))
        if case.lookup_error:
            raise DBException("private DB detail")
        return case.state

    async def normal_auth() -> Auth:
        return case.normal_auth

    async def sandbox_auth() -> Auth:
        return case.sandbox_auth

    monkeypatch.setattr(
        PostgreSQLOrderCrossSellDataMapper, "get_cross_sell_state", lookup
    )
    monkeypatch.setattr(composition, "DATABASE_URL", "normal-db")
    monkeypatch.setattr(auth, "_access_token", None)
    monkeypatch.setattr(auth, "_credentials_key", None)
    monkeypatch.setattr(auth, "_token_lock", asyncio.Lock())
    normal = create_api_application("Normal")
    sandbox = create_sandbox_application(
        SandboxSettings("sandbox-db", "test-jwt", b"test-fingerprint")
    )
    normal.mount("/sandbox", sandbox)
    normal.dependency_overrides[get_auth_service] = normal_auth
    sandbox.dependency_overrides[get_auth_service] = sandbox_auth
    settings = SalesforceSettings(
        "https://unit.my.salesforce.com/token",
        "https://unit.my.salesforce.com/customer",
        "client",
        "secret",
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(case.remote)) as remote:
        monkeypatch.setattr(
            composition,
            "SalesforceMarketingAPI",
            lambda: SalesforceMarketingAPI(settings, remote),
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=normal), base_url="http://test"
        ) as client:
            client.headers["Authorization"] = "Bearer normal-token"
            yield client, case


@pytest.mark.anyio
@pytest.mark.parametrize(("prefix", "env"), [("", "normal"), ("/sandbox", "sandbox")])
async def test_posts_only_flow_one_to_marketing(
    scenario: tuple[httpx.AsyncClient, Scenario], prefix: str, env: str
) -> None:
    http, case = scenario
    response = await http.post(
        prefix + _PATH, json=_BODY, headers={"Authorization": f"Bearer {env}-token"}
    )
    assert response.status_code == 201
    assert response.json() == _RECEIPT
    assert case.reads == [(f"{env}-db", 1001)]
    token_request, marketing_request = case.requests
    assert token_request.url.path == "/token"
    assert marketing_request.headers["Authorization"] == "Bearer fake-token-1"
    assert json.loads(marketing_request.content) == {
        "customer_id": "4",
        "order_id": 1001,
        "related_product": ["117", "118", "123"],
    }


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("state", "code"),
    [
        (None, 404),
        (OrderCrossSellState(4, "CONFIRMED", 25), 409),
        (OrderCrossSellState(4, None, 25), 409),
        (OrderCrossSellState(4, "ACCEPTED", None), 409),
        (OrderCrossSellState(4, "ACCEPTED", 0), 409),
        (OrderCrossSellState(4, "ACCEPTED", -5), 409),
        (OrderCrossSellState(None, "ACCEPTED", 25), 409),
        (OrderCrossSellState(0, "ACCEPTED", 25), 409),
    ],
)
async def test_order_gate_before_oauth_or_delivery(
    scenario: tuple[httpx.AsyncClient, Scenario],
    state: OrderCrossSellState | None,
    code: int,
) -> None:
    http, case = scenario
    case.state = state
    assert (await http.post(_PATH, json=_BODY)).status_code == code
    assert case.reads == [("normal-db", 1001)]
    assert case.requests == []


@pytest.mark.anyio
async def test_authentication_and_payload_before_lookup(
    scenario: tuple[httpx.AsyncClient, Scenario],
) -> None:
    http, case = scenario
    assert (await http.post("/sandbox" + _PATH, json=_BODY)).status_code == 401
    case.normal_auth.role = Role.ADMIN
    assert (await http.post(_PATH, json=_BODY)).status_code == 403
    case.normal_auth.role = Role.INTEGRATION
    for invalid in (
        {},
        {**_BODY, "related_product2": None},
        {**_BODY, "related_product2": []},
        {**_BODY, "customer_id": "4"},
        {**_BODY, "related_product": ["117", "118"]},
        {**_BODY, "related_product": ["117", "117", "118"]},
        {**_BODY, "related_product": ["117", "118", "0"]},
    ):
        assert (await http.post(_PATH, json=invalid)).status_code == 422
    assert (await http.post(_PATH.replace("1001", "0"), json=_BODY)).status_code == 422
    assert case.reads == case.requests == []


@pytest.mark.anyio
async def test_oauth_renewal_sends_identical_payload(
    scenario: tuple[httpx.AsyncClient, Scenario],
) -> None:
    http, case = scenario
    case.renew_token = True
    assert (await http.post(_PATH, json=_BODY)).status_code == 201
    first_token, first_post, second_token, second_post = case.requests
    assert first_token.url == second_token.url
    assert first_post.content == second_post.content
    assert second_post.headers["Authorization"] == "Bearer fake-token-3"


@pytest.mark.anyio
@pytest.mark.parametrize(
    "failure", ["db", "settings", "timeout", "rejected", "receipt"]
)
async def test_failure_status_and_no_delivery_retry(
    scenario: tuple[httpx.AsyncClient, Scenario],
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    http, case = scenario
    expected = {
        "db": 503,
        "settings": 503,
        "timeout": 504,
        "rejected": 502,
        "receipt": 502,
    }
    if failure == "settings":

        def no_settings() -> SalesforceSettings:
            raise SalesforceConfigurationException("Invalid settings")

        monkeypatch.setattr(
            composition, "SalesforceMarketingAPI", SalesforceMarketingAPI
        )
        monkeypatch.setattr(SalesforceSettings, "load", no_settings)
    case.lookup_error = failure == "db"
    case.timeout = failure == "timeout"
    if failure == "rejected":
        case.remote_code = 400
        case.remote_body = {"message": "private rejection detail"}
    if failure == "receipt":
        case.remote_body["flow"] = "cross_sell_products"

    response = await http.post(_PATH, json=_BODY)
    assert response.status_code == expected[failure]
    assert "private" not in response.text
    assert len(case.requests) == (0 if failure in {"db", "settings"} else 2)
