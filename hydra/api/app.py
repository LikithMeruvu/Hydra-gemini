"""FastAPI application factory with lifespan, middleware, and route registration."""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from hydra.__version__ import __version__
from hydra.core.config import get_settings
from hydra.core.redis_client import close_redis
from hydra.services.api_key_service import APIKeyService
from hydra.services.gemini_client import GeminiClient
from hydra.services.health_monitor import HealthMonitor
from hydra.services.rate_limiter import RateLimiter
from hydra.services.router_service import RouterService
from hydra.services.stats_service import StatsService
from hydra.services.token_service import TokenService

logger = logging.getLogger(__name__)

# ── Shared service instances (populated during lifespan) ───────────────────
gemini_client: GeminiClient | None = None
key_service: APIKeyService | None = None
rate_limiter: RateLimiter | None = None
router_service: RouterService | None = None
stats_service: StatsService | None = None
health_monitor: HealthMonitor | None = None
token_service: TokenService | None = None
_start_time: float = 0.0


def get_start_time() -> float:
    return _start_time


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    global gemini_client, key_service, rate_limiter, router_service
    global stats_service, health_monitor, token_service, _start_time

    _start_time = time.time()
    settings = get_settings()

    # Create service instances
    gemini_client = GeminiClient()
    key_service = APIKeyService(gemini_client)
    rate_limiter = RateLimiter()
    router_service = RouterService(
        key_service,
        rate_limiter,
        health_weight=settings.health_weight,
        capacity_weight=settings.capacity_weight,
    )
    stats_service = StatsService()
    health_monitor = HealthMonitor(key_service, rate_limiter, gemini_client)
    token_service = TokenService()

    # Start background workers
    health_monitor.start()
    logger.info("Hydra Gateway v%s started on %s:%d", __version__, settings.host, settings.port)

    yield

    # Shutdown
    await health_monitor.stop()
    await close_redis()
    logger.info("Hydra Gateway stopped")


# ── Auth configuration ─────────────────────────────────────────────────────
PUBLIC_PATHS = frozenset({"/health", "/docs"})       # No auth ever
LOCAL_ONLY_PATHS = frozenset({"/"})                  # Dashboard — localhost only
LOCAL_ONLY_PREFIXES = ("/admin/",)                   # Admin panel — localhost only
API_PATHS = ("/v1/",)                                # API — require Bearer token when tokens exist

_LOCAL_IPS = {"127.0.0.1", "::1", "localhost"}


def _is_local(request: Request) -> bool:
    """Check if request comes from localhost."""
    client = request.client
    if not client:
        return False
    return client.host in _LOCAL_IPS


def create_app() -> FastAPI:
    """Build and return the FastAPI application."""
    app = FastAPI(
        title="Hydra Gateway",
        description="GeminiHydra — OpenAI-compatible Gemini API gateway",
        version=__version__,
        lifespan=lifespan,
        docs_url="/swagger",   # Move Swagger to /swagger (was conflicting with our /docs)
        redoc_url=None,        # Disable redoc
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Security middleware ────────────────────────────────────────────────
    @app.middleware("http")
    async def security_middleware(request: Request, call_next):
        """Auth + access control.

        Security model:
        - /health         → public, no auth
        - /               → localhost only (dashboard)
        - /admin/*        → localhost only (key/token management)
        - /v1/*           → if tokens exist, require Bearer token
                            if no tokens exist, open (local-only mode)
        """
        path = request.url.path
        request.state.bearer_token = None

        # 1. Public paths — always accessible
        if path in PUBLIC_PATHS:
            return await call_next(request)

        # 2. Local-only paths — block remote access
        if path in LOCAL_ONLY_PATHS or any(path.startswith(p) for p in LOCAL_ONLY_PREFIXES):
            if not _is_local(request):
                return JSONResponse(
                    status_code=403,
                    content={"error": "Admin panel is only accessible from localhost"},
                )
            return await call_next(request)

        # 3. API paths — require Bearer token when tokens exist
        if any(path.startswith(p) for p in API_PATHS):
            if token_service:
                has_tokens = await token_service.has_any_tokens()
                if has_tokens:
                    auth = request.headers.get("authorization", "")
                    if not auth.startswith("Bearer "):
                        return JSONResponse(
                            status_code=401,
                            content={"error": "API token required. Set Authorization: Bearer <your-token>"},
                        )
                    token = auth[7:]
                    entry = await token_service.validate_token(token)
                    if not entry:
                        return JSONResponse(
                            status_code=401,
                            content={"error": "Invalid or revoked API token"},
                        )
                    request.state.bearer_token = token

        return await call_next(request)

    # Register routes
    from hydra.api.routes.chat import router as chat_router
    from hydra.api.routes.admin import router as admin_router
    from hydra.api.routes.health import router as health_router
    from hydra.api.routes.embed import router as embed_router
    from hydra.api.routes.models import router as models_router
    from hydra.api.routes.tokens import router as tokens_router

    app.include_router(chat_router)
    app.include_router(admin_router)
    app.include_router(health_router)
    app.include_router(embed_router)
    app.include_router(models_router)
    app.include_router(tokens_router)

    # Serve dashboard UI
    from pathlib import Path
    from fastapi.responses import HTMLResponse
    from fastapi.staticfiles import StaticFiles

    static_dir = Path(__file__).parent / "static"
    
    # Mount static files for logos/JS/CSS
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def serve_dashboard():
        html_path = static_dir / "index.html"
        return HTMLResponse(html_path.read_text(encoding="utf-8"))

    @app.get("/docs", response_class=HTMLResponse, include_in_schema=False)
    async def serve_docs():
        """Public API docs — accessible even by remote users."""
        docs_path = static_dir / "docs.html"
        return HTMLResponse(docs_path.read_text(encoding="utf-8"))

    return app
