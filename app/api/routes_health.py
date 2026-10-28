"""Health-check route."""
from __future__ import annotations

from fastapi import APIRouter

from app.core.config import get_settings
from app.core.model_registry import list_models
from app.models.response_models import HealthResponse

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    settings = get_settings()
    models = list_models()
    return HealthResponse(
        status="ok",
        version=settings.app_version,
        provider_configured=bool(settings.groq_api_key),
        models={k: v.is_available for k, v in models.items()},
    )
