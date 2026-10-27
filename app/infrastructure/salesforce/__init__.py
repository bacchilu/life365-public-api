"""Outbound Salesforce adapters, shared by normal and sandbox composition."""

from .client import SalesforceCustomerAPI
from .settings import SalesforceSettings

__all__ = ["SalesforceCustomerAPI", "SalesforceSettings"]
