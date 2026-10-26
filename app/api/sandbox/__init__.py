"""Mount shared routes with application-local dependency overrides."""

import logging

import psycopg
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from app.api.application import create_api_application
from app.api.customers.routes import get_customer_service
from app.api.dependencies import get_auth_service
from app.api.health.routes import get_health_service
from app.api.integrations.routes import get_customer_synchronization_service
from app.api.orders.routes import get_order_service
from app.api.products.composition import get_products_service
from app.application.exceptions import DBException, ExternalIntegrationDisabledException
from app.application.services.auth_service import AuthService
from app.application.services.customer_service import CustomerService
from app.application.services.customer_synchronization_service import (
    CustomerSynchronizationService,
)
from app.application.services.health_service import HealthService
from app.application.services.order_service import OrderService
from app.application.services.products_service import ProductsService

from .services import SandboxServices
from .settings import SandboxConfigurationError, SandboxSettings

logger = logging.getLogger(__name__)


def create_sandbox_application(settings: SandboxSettings | None = None) -> FastAPI:
    sandbox = create_api_application("Life365 Public API Sandbox")
    sandbox.description = (
        "Isolated local PostgreSQL sandbox using the same endpoint contracts. "
        "Tokens and in-memory sessions are sandbox-only. Product recommendations "
        "return 501; no external business service is called. Run a single worker."
    )
    try:
        services = SandboxServices(
            settings if settings is not None else SandboxSettings.load()
        )
    except SandboxConfigurationError as exc:
        logger.warning("Sandbox unavailable: %s", exc)
        services = None
    sandbox.state.sandbox_services = services

    def require_services() -> SandboxServices:
        if services is None:
            raise HTTPException(status_code=503, detail="Sandbox is not configured")
        return services

    async def auth() -> AuthService:
        return require_services().auth

    async def customers() -> CustomerService:
        return require_services().customers

    async def orders() -> OrderService:
        return require_services().orders

    async def products() -> ProductsService:
        return require_services().products

    async def health() -> HealthService:
        return require_services().health

    async def synchronize(request: Request) -> CustomerSynchronizationService:
        return require_services().customer_synchronization(
            request.client.host if request.client is not None else None
        )

    sandbox.dependency_overrides.update(
        {
            get_auth_service: auth,
            get_customer_service: customers,
            get_order_service: orders,
            get_products_service: products,
            get_health_service: health,
            get_customer_synchronization_service: synchronize,
        }
    )

    async def external_disabled(_request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=501, content={"detail": str(exc)})

    async def persistence_unavailable(
        _request: Request, _exc: Exception
    ) -> JSONResponse:
        return JSONResponse(
            status_code=503, content={"detail": "Sandbox persistence is unavailable"}
        )

    sandbox.add_exception_handler(
        ExternalIntegrationDisabledException, external_disabled
    )
    sandbox.add_exception_handler(DBException, persistence_unavailable)
    sandbox.add_exception_handler(psycopg.Error, persistence_unavailable)
    return sandbox
