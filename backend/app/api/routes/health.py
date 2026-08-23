from datetime import UTC, datetime

from fastapi import APIRouter

from app.core.config import settings
from app.schemas.health import HealthResponse
from app.services.local_app_control import is_local_app_control_ready

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
        local_control_enabled=is_local_app_control_ready(),
        checked_at=datetime.now(UTC),
    )
