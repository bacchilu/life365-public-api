from fastapi import APIRouter

from app.api.products.recommendations import router as recommendations_router
from app.api.products.routes import ProductResponse, router as products_router

router: APIRouter = APIRouter()
router.include_router(recommendations_router)
router.include_router(products_router)

__all__ = ["ProductResponse", "router"]
