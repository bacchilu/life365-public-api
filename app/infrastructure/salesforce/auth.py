"""Process-local token cache, shared by the two API environments."""

import asyncio

import httpx

from app.application.exceptions import (
    SalesforceRequestException,
    SalesforceTimeoutException,
)

from .settings import SalesforceSettings

_access_token: str | None = None
_credentials_key: tuple[str, str, str] | None = None
_token_lock = asyncio.Lock()


async def get_access_token(
    client: httpx.AsyncClient, settings: SalesforceSettings
) -> str:
    global _access_token, _credentials_key
    key = (settings.token_url, settings.client_id, settings.client_secret)
    async with _token_lock:
        if _access_token is not None and _credentials_key == key:
            return _access_token
        try:
            response = await client.post(
                settings.token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": settings.client_id,
                    "client_secret": settings.client_secret,
                },
                timeout=settings.timeout_seconds,
                follow_redirects=False,
            )
        except httpx.TimeoutException:
            raise SalesforceTimeoutException(
                "Salesforce authentication timed out; no customer event was sent"
            ) from None
        except httpx.RequestError:
            raise SalesforceRequestException(
                "Salesforce authentication is unavailable; no customer event was sent"
            ) from None
        if response.status_code != 200:
            raise SalesforceRequestException(
                f"Salesforce authentication failed (HTTP {response.status_code}); no customer event was sent",
                remote_status=response.status_code,
            )
        try:
            payload = response.json()
        except ValueError:
            raise SalesforceRequestException(
                "Salesforce returned an invalid authentication response"
            ) from None
        token = payload.get("access_token") if isinstance(payload, dict) else None
        if not isinstance(token, str) or not token.strip():
            raise SalesforceRequestException("Salesforce returned no access token")
        _access_token, _credentials_key = token, key
        return token


def invalidate_access_token(settings: SalesforceSettings, used_token: str) -> None:
    global _access_token, _credentials_key
    key = (settings.token_url, settings.client_id, settings.client_secret)
    if _credentials_key == key and _access_token == used_token:
        _access_token, _credentials_key = None, None
