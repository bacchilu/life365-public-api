"""Outbound Salesforce adapters, shared by normal and sandbox composition."""

from .client import SalesforceCustomerAPI
from .product_client import SalesforceProductAPI
from .settings import SalesforceSettings

__all__ = ["SalesforceCustomerAPI", "SalesforceProductAPI", "SalesforceSettings"]
