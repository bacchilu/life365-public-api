import httpx
import pytest

from app.infrastructure.life365_portal_api import Life365PortalAPI


@pytest.mark.parametrize(
    ("order_id", "customer_id", "expected_query"),
    [
        (1008020, None, "order_id=1008020"),
        (None, 40250, "customer_id=40250"),
    ],
)
@pytest.mark.anyio
async def test_recommend_products_fetches_portal_api(
    order_id: int | None,
    customer_id: int | None,
    expected_query: str,
) -> None:
    requests: list[httpx.Request] = []

    def handle_request(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=[])

    transport = httpx.MockTransport(handle_request)
    async with httpx.AsyncClient(transport=transport) as client:
        gateway = Life365PortalAPI(http_client=client)

        await gateway.recommend_products(
            order_id=order_id,
            customer_id=customer_id,
        )

    assert len(requests) == 1
    request = requests[0]
    assert request.method == "GET"
    assert str(request.url) == (
        f"https://b2b.life365.eu/api/upsell/recommend?{expected_query}"
    )
    assert request.headers["Authorization"].startswith("Bearer ")
