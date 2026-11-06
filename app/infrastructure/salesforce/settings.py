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
    product_url: str | None = None
    order_url: str | None = None

    @property
    def order_sync_url(self) -> str:
        if self.order_url is not None:
            return self.order_url
        token = urlsplit(self.token_url)
        return f"{token.scheme}://{token.netloc}/services/apexrest/order/sync/"

    @property
    def product_sync_url(self) -> str:
        if self.product_url is not None:
            return self.product_url
        token = urlsplit(self.token_url)
        return f"{token.scheme}://{token.netloc}/services/apexrest/product/sync/"

    def __post_init__(self) -> None:
        try:
            token = urlsplit(self.token_url)
            customer = urlsplit(self.customer_url)
            product = urlsplit(self.product_sync_url)
            order = urlsplit(self.order_sync_url)
            token_origin = (token.hostname, token.port or 443)
            customer_origin = (customer.hostname, customer.port or 443)
            product_origin = (product.hostname, product.port or 443)
            order_origin = (order.hostname, order.port or 443)
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
            for url in (token, customer, product, order)
        ):
            raise SalesforceConfigurationException(
                "Salesforce URLs must be absolute HTTPS URLs without credentials, query, or fragment"
            )
        if any(
            origin != token_origin
            for origin in (customer_origin, product_origin, order_origin)
        ):
            raise SalesforceConfigurationException(
                "Salesforce token and synchronization URLs must have the same origin"
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
                product_url=values.get("SALESFORCE_PRODUCT_SYNC_URL") or None,
                order_url=values.get("SALESFORCE_ORDER_SYNC_URL") or None,
            )
        except (ValueError, TypeError):
            raise SalesforceConfigurationException(
                "Invalid Salesforce connection configuration"
            ) from None
