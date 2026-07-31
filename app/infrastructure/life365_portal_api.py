import httpx

from app.application.dtos import ProductRecommendation
from app.application.ports import Life365APIGateway

_RECOMMEND_URL = "https://b2b.life365.eu/api/upsell/recommend"
_API_TOKEN = "RXfmK6tpf4LDS2WrXB71AxMIpZfy8I3RUjrlpzqCOoQ"
_TIMEOUT_SECONDS = 10.0


def _required_string(payload: dict[object, object], field: str) -> str:
    value: object | None = payload.get(field)
    if not isinstance(value, str):
        raise TypeError(f"Invalid product recommendation field: {field}")

    return value


def _optional_string(payload: dict[object, object], field: str) -> str | None:
    value: object | None = payload.get(field)
    if value is not None and not isinstance(value, str):
        raise ValueError(f"Invalid product recommendation field: {field}")

    return value


def _parse_recommendation(payload: object) -> ProductRecommendation:
    if not isinstance(payload, dict):
        raise TypeError("Invalid product recommendation response")

    return ProductRecommendation(
        code=_optional_string(payload, "code"),
        name=_required_string(payload, "name"),
        image_url=_optional_string(payload, "image_url"),
        description=_required_string(payload, "description"),
        product_url=_required_string(payload, "product_url"),
    )


def _parse_recommendations(payload: object) -> list[ProductRecommendation]:
    if not isinstance(payload, list):
        raise TypeError("Invalid product recommendations response")

    return [_parse_recommendation(item) for item in payload]


class Life365PortalAPI(Life365APIGateway):
    def __init__(self, http_client: httpx.AsyncClient | None = None) -> None:
        self._http_client = http_client

    async def recommend_products(
        self, order_id: int | None = None, customer_id: int | None = None
    ) -> list[ProductRecommendation]:
        params: dict[str, int | None] = (
            {"order_id": order_id}
            if order_id is not None
            else {"customer_id": customer_id}
        )

        if self._http_client is not None:
            return await self._request_recommendations(self._http_client, params)

        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            return await self._request_recommendations(client, params)

    async def _request_recommendations(
        self, client: httpx.AsyncClient, params: dict[str, int | None]
    ) -> list[ProductRecommendation]:
        response: httpx.Response = await client.get(
            _RECOMMEND_URL,
            headers={"Authorization": f"Bearer {_API_TOKEN}"},
            params=params,
        )
        response.raise_for_status()
        return _parse_recommendations(response.json())
