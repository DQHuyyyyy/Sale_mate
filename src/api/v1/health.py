"""Health check — dùng cho Docker HEALTHCHECK và giám sát uptime."""

from __future__ import annotations

from fastapi import APIRouter, Response

from src.api.deps import SettingsDep
from src.core.container import container
from src.models.common import HealthResponse

router = APIRouter(tags=["health"])

APP_VERSION = "0.1.0"


@router.get("/health", response_model=HealthResponse, summary="Kiểm tra sức khoẻ")
async def health(settings: SettingsDep, response: Response) -> HealthResponse:
    """Trả 200 khi khoẻ, 503 khi có thành phần lỗi."""
    from src.agents.contracts import AgentService

    checks = {
        "llm": "configured" if settings.has_openai_key else "fallback",
        "agent": "ready" if container.is_registered(AgentService) else "not_ready",
    }
    degraded = checks["agent"] != "ready"
    if degraded:
        response.status_code = 503

    return HealthResponse(
        status="degraded" if degraded else "healthy",
        version=APP_VERSION,
        environment=settings.app_env,
        checks=checks,
    )


@router.get("/health/live", summary="Liveness probe")
async def liveness() -> dict[str, str]:
    return {"status": "alive"}
