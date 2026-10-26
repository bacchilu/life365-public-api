"""Register the same route implementations in independently configured APIs."""

from fastapi import FastAPI

from app.api.auth import router as auth_router
from app.api.customers import router as customers_router
from app.api.health import router as health_router
from app.api.integrations import router as integrations_router
from app.api.orders import router as orders_router
from app.api.products import router as products_router


def create_api_application(title: str) -> FastAPI:
    application = FastAPI(title=title, version="0.1.0")
    for router in (
        auth_router,
        customers_router,
        health_router,
        integrations_router,
        orders_router,
        products_router,
    ):
        application.include_router(router)
    return application
