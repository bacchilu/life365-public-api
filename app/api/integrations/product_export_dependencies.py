"""Compose product exports with the selected database and the real remote API."""

from typing import Annotated

from fastapi import Depends, HTTPException

from app.application.domain import AuthenticatedUser
from app.application.exceptions import SalesforceConfigurationException
from app.application.services.product_export_service import ProductExportService
from app.infrastructure.data_mapper.connection import DATABASE_URL
from app.infrastructure.data_mapper.product_export import (
    PostgreSQLProductExportDataMapper,
)
from app.infrastructure.salesforce import SalesforceProductAPI, SalesforceSettings

from .dependencies import get_integration_user

_salesforce_product_gateway: SalesforceProductAPI | None = None


def get_salesforce_product_gateway() -> SalesforceProductAPI:
    global _salesforce_product_gateway
    if _salesforce_product_gateway is None:
        _salesforce_product_gateway = SalesforceProductAPI(SalesforceSettings.load())
    return _salesforce_product_gateway


async def get_product_export_service(
    _integration_user: Annotated[AuthenticatedUser, Depends(get_integration_user)],
) -> ProductExportService:
    try:
        gateway = get_salesforce_product_gateway()
    except SalesforceConfigurationException as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    return ProductExportService(
        PostgreSQLProductExportDataMapper(DATABASE_URL), gateway
    )
