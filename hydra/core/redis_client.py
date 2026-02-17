"""Redis connection pool management."""

from __future__ import annotations

import logging
from typing import Optional

import redis.asyncio as aioredis

from hydra.core.config import get_settings

logger = logging.getLogger(__name__)

_pool: Optional[aioredis.Redis] = None


async def get_redis() -> aioredis.Redis:
    """Return the global async Redis client, creating the pool on first call."""
    global _pool
    if _pool is None:
        settings = get_settings()
        _pool = aioredis.from_url(
            settings.redis_url,
            decode_responses=True,
            max_connections=20,
        )
    return _pool


async def check_redis_health() -> bool:
    """Return True if Redis is reachable."""
    try:
        r = await get_redis()
        return await r.ping()
    except Exception as exc:
        logger.warning("Redis health check failed: %s", exc)
        return False


async def close_redis() -> None:
    """Gracefully shut down the Redis connection pool."""
    global _pool
    if _pool is not None:
        await _pool.aclose()
        _pool = None
