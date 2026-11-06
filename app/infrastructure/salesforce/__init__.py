"""Outbound Salesforce adapters, shared by normal and sandbox composition."""

from .client import SalesforceCustomerAPI
from .order_client import SalesforceOrderAPI
from .product_client import SalesforceProductAPI
from .settings import SalesforceSettings

__all__ = [
    "SalesforceCustomerAPI",
    "SalesforceOrderAPI",
    "SalesforceProductAPI",
    "SalesforceSettings",
]
