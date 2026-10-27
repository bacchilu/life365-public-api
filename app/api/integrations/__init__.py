from fastapi import APIRouter

from app.api.integrations.exports import router as export_router
from app.api.integrations.routes import router as event_router

router = APIRouter()
router.include_router(event_router)
router.include_router(export_router)

__all__ = ["router"]
