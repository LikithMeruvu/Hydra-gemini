"""GET /health — system health check."""

from __future__ import annotations

import time

from fastapi import APIRouter

from hydra.__version__ import __version__
from hydra.core.redis_client import check_redis_health
from hydra.models.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Return system health status."""
    from hydra.api.app import key_service, get_start_time

    redis_ok = await check_redis_health()
    active = 0
    if key_service and redis_ok:
        try:
            active = await key_service.get_key_count()
        except Exception:
            pass

    uptime = time.time() - get_start_time()

    return HealthResponse(
        status="ok" if redis_ok else "degraded",
        redis_connected=redis_ok,
        active_keys=active,
        uptime_seconds=round(uptime, 1),
        version=__version__,
    )
