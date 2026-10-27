"""Explicit remote configuration; values are never included in error text."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import dotenv_values

from app.application.exceptions import SalesforceConfigurationException


@dataclass(frozen=True, slots=True)
class SalesforceSettings:
    token_url: str
    customer_url: str
    client_id: str = field(repr=False)
    client_secret: str = field(repr=False)
    timeout_seconds: float = 30.0

    def __post_init__(self) -> None:
        try:
            token = urlsplit(self.token_url)
            customer = urlsplit(self.customer_url)
            token_origin = (token.hostname, token.port or 443)
            customer_origin = (customer.hostname, customer.port or 443)
        except ValueError:
            raise SalesforceConfigurationException(
                "Invalid Salesforce URL configuration"
            ) from None
        if any(
            url.scheme != "https"
            or not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
            for url in (token, customer)
        ):
            raise SalesforceConfigurationException(
                "Salesforce URLs must be absolute HTTPS URLs without credentials, query, or fragment"
            )
        if token_origin != customer_origin:
            raise SalesforceConfigurationException(
                "Salesforce token and customer URLs must have the same origin"
            )
        if not self.client_id.strip() or not self.client_secret.strip():
            raise SalesforceConfigurationException(
                "Salesforce credentials must be configured"
            )
        if not 0 < self.timeout_seconds <= 120:
            raise SalesforceConfigurationException(
                "Salesforce timeout must be greater than zero and at most 120 seconds"
            )

    @classmethod
    def load(cls) -> "SalesforceSettings":
        values = {
            **dotenv_values(Path(__file__).resolve().parents[3] / ".env"),
            **os.environ,
        }
        token_url = values.get("SALESFORCE_TOKEN_URL", "") or ""
        try:
            token = urlsplit(token_url)
            customer_url = (
                values.get("SALESFORCE_CUSTOMER_SYNC_URL")
                or f"{token.scheme}://{token.netloc}/services/apexrest/customer/sync/"
            )
            return cls(
                token_url,
                customer_url,
                values.get("SALESFORCE_CLIENT_ID") or "",
                values.get("SALESFORCE_CLIENT_SECRET") or "",
                float(values.get("SALESFORCE_TIMEOUT_SECONDS") or "30"),
            )
        except (ValueError, TypeError):
            raise SalesforceConfigurationException(
                "Invalid Salesforce connection configuration"
            ) from None
