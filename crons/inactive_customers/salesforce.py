import httpx


async def _request_access_token(
    client: httpx.AsyncClient,
    token_url: str,
    client_id: str,
    client_secret: str,
) -> str:
    response: httpx.Response = await client.post(
        token_url,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        },
    )
    response.raise_for_status()

    payload: object = response.json()
    access_token: object = (
        payload.get("access_token") if isinstance(payload, dict) else None
    )
    if not isinstance(access_token, str) or not access_token:
        raise RuntimeError("Salesforce response does not contain an access token")

    return access_token


async def request_salesforce_access_token(
    token_url: str,
    client_id: str,
    client_secret: str,
    client: httpx.AsyncClient | None = None,
) -> str:
    if client is not None:
        return await _request_access_token(
            client, token_url, client_id, client_secret
        )

    async with httpx.AsyncClient(timeout=30.0) as managed_client:
        return await _request_access_token(
            managed_client,
            token_url,
            client_id,
            client_secret,
        )
