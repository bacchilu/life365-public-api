import httpx

from app.application.ports import Life365APIGateway

_RECOMMEND_URL = "https://b2b.life365.eu/api/upsell/recommend"
_API_TOKEN = "RXfmK6tpf4LDS2WrXB71AxMIpZfy8I3RUjrlpzqCOoQ"
_TIMEOUT_SECONDS = 10.0


class Life365PortalAPI(Life365APIGateway):
    def __init__(self, http_client: httpx.AsyncClient | None = None) -> None:
        self._http_client = http_client

    async def recommend_products(
        self, order_id: int | None = None, customer_id: int | None = None
    ) -> object:
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
    ) -> object:
        response: httpx.Response = await client.get(
            _RECOMMEND_URL,
            headers={"Authorization": f"Bearer {_API_TOKEN}"},
            params=params,
        )
        response.raise_for_status()
        return response.json()
