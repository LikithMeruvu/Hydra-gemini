"""Request logging middleware — writes every request to Redis."""

from __future__ import annotations

import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Logs request method, path, status, and latency."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        t0 = time.perf_counter()
        response = await call_next(request)
        elapsed = int((time.perf_counter() - t0) * 1000)

        logger.info(
            "%s %s → %d (%dms)",
            request.method,
            request.url.path,
            response.status_code,
            elapsed,
        )
        return response
