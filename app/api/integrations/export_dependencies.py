"""Compose outbound services without changing the incoming synchronization."""

from typing import Annotated

from fastapi import Depends, HTTPException

from app.application.domain import AuthenticatedUser
from app.application.exceptions import SalesforceConfigurationException
from app.application.services.customer_export_service import CustomerExportService
from app.infrastructure.data_mapper.connection import DATABASE_URL
from app.infrastructure.data_mapper.customer_export import (
    PostgreSQLCustomerExportDataMapper,
)
from app.infrastructure.salesforce import SalesforceCustomerAPI, SalesforceSettings

from .dependencies import get_integration_user

_salesforce_gateway: SalesforceCustomerAPI | None = None


def get_salesforce_customer_gateway() -> SalesforceCustomerAPI:
    global _salesforce_gateway
    if _salesforce_gateway is None:
        _salesforce_gateway = SalesforceCustomerAPI(SalesforceSettings.load())
    return _salesforce_gateway


async def get_customer_export_service(
    _integration_user: Annotated[AuthenticatedUser, Depends(get_integration_user)],
) -> CustomerExportService:
    try:
        gateway = get_salesforce_customer_gateway()
    except SalesforceConfigurationException as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    return CustomerExportService(
        PostgreSQLCustomerExportDataMapper(DATABASE_URL), gateway
    )
