from fastapi import APIRouter
from pydantic import BaseModel

from app.application.services.health_service import HealthService
from app.infrastructure.data_mapper import DATABASE_URL, DataMapper

router: APIRouter = APIRouter(tags=["health"])
data_mapper: DataMapper = DataMapper(DATABASE_URL)
health_service: HealthService = HealthService(data_mapper)


class HealthResponse(BaseModel):
    status: str
    db: str


@router.get("/health", summary="Health check")
async def health() -> HealthResponse:
    """
    Check whether the application is running and can connect to the database.
    """
    return HealthResponse(
        status="ok" if health_service.health() else "ko",
        db="ok" if await health_service.check_db() else "ko",
    )
