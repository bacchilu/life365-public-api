from fastapi import APIRouter
from pydantic import BaseModel

from app.application.ports import CheckGateway
from app.application.services.health_service import HealthService
from app.infrastructure.data_mapper import DATABASE_URL, CheckDataMapper

router: APIRouter = APIRouter(tags=["health"])
check_gateway: CheckGateway = CheckDataMapper(DATABASE_URL)
health_service: HealthService = HealthService(check_gateway)


class HealthResponse(BaseModel):
    status: str
    db: str


@router.get("/health", summary="Health check", response_model=HealthResponse)
async def health() -> dict[str, str]:
    """
    Check whether the application is running and can connect to the database.
    """
    return {
        "status": "ok" if health_service.health() else "ko",
        "db": "ok" if await health_service.check_db() else "ko",
    }
