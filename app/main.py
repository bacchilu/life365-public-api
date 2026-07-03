from fastapi import FastAPI

from app.api.auth import router as auth_router
from app.api.customers import router as customers_router
from app.api.health import router as health_router
from app.api.products import router as products_router

app: FastAPI = FastAPI(title="Life365 Public API", version="0.1.0")

app.include_router(auth_router)
app.include_router(customers_router)
app.include_router(health_router)
app.include_router(products_router)
