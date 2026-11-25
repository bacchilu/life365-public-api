"""Exercise the Flow 2 route and adapter without outgoing network requests."""

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

import httpx
import pytest

from app.api.application import create_api_application
from app.api.dependencies import get_auth_service
from app.api.integrations import customer_reactivation_dependencies as composition
from app.api.sandbox import create_sandbox_application
from app.api.sandbox.settings import SandboxSettings
from app.application.domain import Role
from app.application.exceptions import DBException
from app.infrastructure.data_mapper.customer_reactivation import (
    PostgreSQLCustomerReactivationDataMapper,
)
from app.infrastructure.salesforce import SalesforceSettings, auth
from app.infrastructure.salesforce.marketing_client import SalesforceMarketingAPI
from tests.test_product_export_api import Auth

_PATH = "/integrations/salesforce/customers/2/marketing/reactivation"
_BODY = {
    "related_product": ["104", "101", "103", "102"],
    "related_product2": ["108", "105", "107", "106"],
}


@dataclass
class Scenario:
    inactive: bool | None = True
    lookup_error: bool = False
    failure: str = ""
    reads: list[tuple[str, int]] = field(default_factory=list)
    posts: list[httpx.Request] = field(default_factory=list)
    token_requests: int = 0
    normal_auth: Auth = field(default_factory=lambda: Auth("normal-token"))
    sandbox_auth: Auth = field(default_factory=lambda: Auth("sandbox-token"))

    def remote(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/token":
            self.token_requests += 1
            return httpx.Response(
                200, json={"access_token": f"fake-token-{self.token_requests}"}
            )
        assert request.url.path == "/services/apexrest/marketing/products/"
        assert request.method == "POST"
        self.posts.append(request)
        if self.failure == "expired" and len(self.posts) == 1:
            return httpx.Response(401)
        if self.failure == "timeout":
            raise httpx.ReadTimeout("private detail")
        if self.failure == "rejected":
            return httpx.Response(400, json={"message": "private detail"})
        payload = json.loads(request.content)
        count = len(payload["related_product"]) + len(payload["related_product2"])
        records = [f"record-{i}" for i in range(1, count + 1)]
        if self.failure == "wrong count":
            records.pop()
        return httpx.Response(
            201,
            json={
                "success": True,
                "flow": "recommended_products"
                if self.failure == "wrong flow"
                else "cross_sell_products",
                "recordsCreated": count,
                "recordIds": records,
            },
        )


@pytest.fixture
async def scenario(
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[tuple[httpx.AsyncClient, Scenario]]:
    case = Scenario()

    async def lookup(
        self: PostgreSQLCustomerReactivationDataMapper, customer_id: int
    ) -> bool | None:
        case.reads.append((self._connection_string, customer_id))
        if case.lookup_error:
            raise DBException("private detail")
        return case.inactive

    monkeypatch.setattr(PostgreSQLCustomerReactivationDataMapper, "is_inactive", lookup)
    monkeypatch.setattr(composition, "DATABASE_URL", "normal-db")
    monkeypatch.setattr(auth, "_access_token", None)
    monkeypatch.setattr(auth, "_credentials_key", None)
    monkeypatch.setattr(auth, "_token_lock", asyncio.Lock())
    normal = create_api_application("Normal")
    sandbox = create_sandbox_application(
        SandboxSettings("sandbox-db", "test-jwt", b"test-fingerprint")
    )
    normal.mount("/sandbox", sandbox)
    normal.dependency_overrides[get_auth_service] = lambda: case.normal_auth
    sandbox.dependency_overrides[get_auth_service] = lambda: case.sandbox_auth
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
@pytest.mark.parametrize("follow_up", [_BODY["related_product2"], []])
async def test_forwards_both_lists_unchanged(
    scenario: tuple[httpx.AsyncClient, Scenario],
    prefix: str,
    env: str,
    follow_up: list[str],
) -> None:
    http, case = scenario
    body = {**_BODY, "related_product2": follow_up}
    response = await http.post(
        prefix + _PATH, json=body, headers={"Authorization": f"Bearer {env}-token"}
    )
    count = 4 + len(follow_up)
    assert response.status_code == 201
    assert response.json() == {
        "success": True,
        "flow": "cross_sell_products",
        "recordsCreated": count,
        "recordIds": [f"record-{i}" for i in range(1, count + 1)],
    }
    assert case.reads == [(f"{env}-db", 2)]
    assert case.token_requests == 1
    (request,) = case.posts
    assert json.loads(request.content) == {"customer_id": "2", **body}


@pytest.mark.anyio
@pytest.mark.parametrize(("state", "status"), [(None, 404), (False, 409)])
async def test_rejects_missing_or_ineligible_customer_before_oauth(
    scenario: tuple[httpx.AsyncClient, Scenario], state: bool | None, status: int
) -> None:
    http, case = scenario
    case.inactive = state
    assert (await http.post(_PATH, json=_BODY)).status_code == status
    assert case.reads == [("normal-db", 2)]
    assert case.token_requests == 0 and not case.posts


@pytest.mark.anyio
async def test_validates_role_and_body_before_database_lookup(
    scenario: tuple[httpx.AsyncClient, Scenario],
) -> None:
    http, case = scenario
    assert (await http.post("/sandbox" + _PATH, json=_BODY)).status_code == 401
    case.normal_auth.role = Role.ADMIN
    assert (await http.post(_PATH, json=_BODY)).status_code == 403
    case.normal_auth.role = Role.INTEGRATION
    for invalid in (
        {"related_product": _BODY["related_product"]},
        {**_BODY, "related_product2": None},
        {**_BODY, "related_product2": ["108"]},
        {**_BODY, "related_product": []},
        {**_BODY, "related_product": [101, "102", "103", "104"]},
        {**_BODY, "related_product": ["0", "102", "103", "104"]},
        {**_BODY, "related_product": ["101", "101", "103", "104"]},
        {**_BODY, "related_product2": _BODY["related_product"]},
        {**_BODY, "order_id": 1001},
        {**_BODY, "customer_id": "2"},
    ):
        assert (await http.post(_PATH, json=invalid)).status_code == 422
    assert case.reads == case.posts == []
    assert case.token_requests == 0


@pytest.mark.anyio
async def test_openapi_requires_both_lists_in_both_environments(
    scenario: tuple[httpx.AsyncClient, Scenario],
) -> None:
    http, _ = scenario
    for prefix in ("", "/sandbox"):
        specification = (await http.get(prefix + "/openapi.json")).json()
        operation = specification["paths"][_PATH.replace("/2/", "/{customer_id}/")][
            "post"
        ]
        ref = operation["requestBody"]["content"]["application/json"]["schema"]["$ref"]
        schema = specification["components"]["schemas"][ref.rsplit("/", 1)[-1]]
        assert set(schema["required"]) == {"related_product", "related_product2"}
        assert schema["additionalProperties"] is False


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("failure", "status"),
    [
        ("expired", 201),
        ("db", 503),
        ("timeout", 504),
        ("rejected", 502),
        ("wrong flow", 502),
        ("wrong count", 502),
    ],
)
async def test_delivery_and_retry_policy(
    scenario: tuple[httpx.AsyncClient, Scenario], failure: str, status: int
) -> None:
    http, case = scenario
    case.failure = failure
    case.lookup_error = failure == "db"
    response = await http.post(_PATH, json=_BODY)
    assert response.status_code == status
    assert "private" not in response.text
    if failure == "expired":
        first, second = case.posts
        assert case.token_requests == 2
        assert first.content == second.content
        assert first.headers["Authorization"] == "Bearer fake-token-1"
        assert second.headers["Authorization"] == "Bearer fake-token-2"
    else:
        expected_attempts = 0 if failure == "db" else 1
        assert case.token_requests == len(case.posts) == expected_attempts
