from fastapi import APIRouter

from app.api.integrations.exports import router as export_router
from app.api.integrations.order_exports import router as order_export_router
from app.api.integrations.product_exports import router as product_export_router
from app.api.integrations.routes import router as event_router

router = APIRouter()
router.include_router(event_router)
router.include_router(export_router)
router.include_router(product_export_router)
router.include_router(order_export_router)

__all__ = ["router"]
