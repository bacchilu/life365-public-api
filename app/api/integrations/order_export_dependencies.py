"""Compose order exports without changing the active database configuration."""

from typing import Annotated

from fastapi import Depends, HTTPException

from app.application.domain import AuthenticatedUser
from app.application.exceptions import SalesforceConfigurationException
from app.application.services.order_export_service import OrderExportService
from app.infrastructure.data_mapper.connection import DATABASE_URL
from app.infrastructure.data_mapper.order_export import PostgreSQLOrderExportDataMapper
from app.infrastructure.salesforce import SalesforceOrderAPI, SalesforceSettings

from .dependencies import get_integration_user

_salesforce_order_gateway: SalesforceOrderAPI | None = None


def get_salesforce_order_gateway() -> SalesforceOrderAPI:
    global _salesforce_order_gateway
    if _salesforce_order_gateway is None:
        _salesforce_order_gateway = SalesforceOrderAPI(SalesforceSettings.load())
    return _salesforce_order_gateway


async def get_order_export_service(
    _integration_user: Annotated[AuthenticatedUser, Depends(get_integration_user)],
) -> OrderExportService:
    try:
        gateway = get_salesforce_order_gateway()
    except SalesforceConfigurationException as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    return OrderExportService(PostgreSQLOrderExportDataMapper(DATABASE_URL), gateway)
