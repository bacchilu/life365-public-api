from urllib.parse import parse_qs

import httpx

from crons.inactive_customers.salesforce import request_salesforce_access_token


def test_request_salesforce_access_token() -> None:
    def handle_request(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url == httpx.URL(
            "https://example.my.salesforce.com/services/oauth2/token"
        )
        assert request.headers["content-type"].startswith(
            "application/x-www-form-urlencoded"
        )
        assert parse_qs(request.content.decode()) == {
            "grant_type": ["client_credentials"],
            "client_id": ["test-client-id"],
            "client_secret": ["test-client-secret"],
        }
        return httpx.Response(200, json={"access_token": "test-access-token"})

    transport = httpx.MockTransport(handle_request)
    with httpx.Client(transport=transport) as client:
        access_token = request_salesforce_access_token(
            "https://example.my.salesforce.com/services/oauth2/token",
            "test-client-id",
            "test-client-secret",
            client=client,
        )

    assert access_token == "test-access-token"
