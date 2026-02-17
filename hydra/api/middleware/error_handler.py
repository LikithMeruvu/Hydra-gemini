"""Global error handler — maps custom exceptions to HTTP status codes."""

from __future__ import annotations

import logging

from fastapi import Request
from fastapi.responses import JSONResponse

from hydra.core.exceptions import (
    AllKeysExhaustedError,
    GeminiAPIError,
    InvalidAPIKeyError,
    RateLimitExceededError,
    RedisConnectionError,
    TUIError,
)

logger = logging.getLogger(__name__)


async def tui_exception_handler(request: Request, exc: TUIError) -> JSONResponse:
    """Map Hydra exceptions to proper HTTP responses."""
    if isinstance(exc, AllKeysExhaustedError):
        return JSONResponse(429, {"error": str(exc), "type": "all_keys_exhausted"})
    if isinstance(exc, RateLimitExceededError):
        return JSONResponse(429, {"error": str(exc), "type": "rate_limited", "model": exc.model})
    if isinstance(exc, InvalidAPIKeyError):
        return JSONResponse(400, {"error": str(exc), "type": "invalid_key", "email": exc.email})
    if isinstance(exc, RedisConnectionError):
        return JSONResponse(503, {"error": str(exc), "type": "redis_unavailable"})
    if isinstance(exc, GeminiAPIError):
        return JSONResponse(502, {"error": str(exc), "type": "gemini_error", "status_code": exc.status_code})

    logger.exception("Unhandled Hydra error: %s", exc)
    return JSONResponse(500, {"error": str(exc), "type": "internal_error"})
