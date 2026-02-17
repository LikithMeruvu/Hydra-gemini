"""Health monitor — background tasks for key health, model re-detection, and RPD resets."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from hydra.core.constants import ALL_MODELS, MODEL_PRIORITY, MODEL_REDETECT_INTERVAL
from hydra.services.api_key_service import APIKeyService
from hydra.services.gemini_client import GeminiClient
from hydra.services.rate_limiter import RateLimiter
from hydra.core.redis_client import get_redis

logger = logging.getLogger(__name__)

_PT_OFFSET = timedelta(hours=-8)


class HealthMonitor:
    """Background worker that monitors API key health, re-detects models, and handles RPD resets."""

    def __init__(
        self,
        key_service: APIKeyService,
        rate_limiter: RateLimiter,
        gemini_client: GeminiClient,
        health_interval: int = 300,  # 5 min
        cleanup_interval: int = 60,  # 1 min
    ):
        self.keys = key_service
        self.rl = rate_limiter
        self.gemini = gemini_client
        self.health_interval = health_interval
        self.cleanup_interval = cleanup_interval
        self.redetect_interval = MODEL_REDETECT_INTERVAL
        self._tasks: list[asyncio.Task] = []

    def start(self) -> None:
        """Launch all background tasks."""
        self._tasks = [
            asyncio.create_task(self._health_loop(), name="health_check"),
            asyncio.create_task(self._cleanup_loop(), name="rate_limit_cleanup"),
            asyncio.create_task(self._rpd_reset_loop(), name="rpd_reset"),
            asyncio.create_task(self._model_redetect_loop(), name="model_redetect"),
        ]
        logger.info("Health monitor started (%d background workers)", len(self._tasks))

    async def stop(self) -> None:
        """Cancel all background tasks."""
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        logger.info("Health monitor stopped")

    # ── loops ──────────────────────────────────────────────────────────────

    async def _health_loop(self) -> None:
        """Periodically test disabled keys for auto-recovery."""
        while True:
            try:
                await asyncio.sleep(self.health_interval)
                all_keys = await self.keys.get_all_keys()
                disabled = {kh: e for kh, e in all_keys.items() if not e.is_active}
                if not disabled:
                    continue

                logger.info("Checking %d disabled keys for recovery...", len(disabled))

                # Get plaintext keys for testing
                r = await get_redis()
                for kh, entry in disabled.items():
                    plain_key = await r.hget("_plainkeys", kh)
                    if not plain_key:
                        continue

                    # Try to use the key with any model
                    for model in entry.available_models or MODEL_PRIORITY[:2]:
                        if await self.gemini.test_api_key(plain_key, model):
                            await self.keys.reactivate_key(kh)
                            logger.info("Key %s (%s) reactivated!", kh[:8], entry.email)
                            break
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Health check error: %s", exc)

    async def _model_redetect_loop(self) -> None:
        """Periodically re-detect available models for all active keys.

        This handles models that appear/disappear dynamically (e.g., Google
        enables/disables a model on their end). Uses the lightweight models.list
        API so it doesn't consume generateContent rate limits.
        """
        while True:
            try:
                await asyncio.sleep(self.redetect_interval)

                r = await get_redis()
                all_keys = await self.keys.get_all_keys()
                active_keys = {kh: e for kh, e in all_keys.items() if e.is_active}

                if not active_keys:
                    continue

                logger.info("Re-detecting models for %d active keys...", len(active_keys))

                for kh, entry in active_keys.items():
                    try:
                        plain_key = await r.hget("_plainkeys", kh)
                        if not plain_key:
                            continue

                        # Use models.list API — lightweight, no rate-limit cost
                        detected = await self.gemini.detect_available_models(plain_key, ALL_MODELS)
                        if detected:
                            updated = await self.keys.update_models(kh, detected)
                            if updated:
                                logger.info(
                                    "Key %s (%s): models updated → %s",
                                    kh[:8], entry.email, detected,
                                )
                    except Exception as exc:
                        logger.warning("Model re-detection failed for %s: %s", kh[:8], exc)

            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Model re-detection loop error: %s", exc)

    async def _cleanup_loop(self) -> None:
        """Remove stale timestamps from sliding windows."""
        while True:
            try:
                await asyncio.sleep(self.cleanup_interval)
                active_keys = await self.keys.get_active_keys()
                for kh, entry in active_keys.items():
                    for model in entry.available_models:
                        await self.rl.cleanup_old_data(kh, model)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Cleanup error: %s", exc)

    async def _rpd_reset_loop(self) -> None:
        """Check every minute if midnight PT has passed and reset RPD counters."""
        last_reset_date = ""
        while True:
            try:
                await asyncio.sleep(60)
                utc_now = datetime.now(timezone.utc)
                pt_now = utc_now + _PT_OFFSET
                pt_date = pt_now.strftime("%Y-%m-%d")

                if pt_date != last_reset_date and pt_now.hour == 0 and pt_now.minute < 2:
                    count = await self.rl.reset_rpd_all()
                    last_reset_date = pt_date
                    logger.info("RPD counters reset for %d rate-limit entries (midnight PT)", count)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("RPD reset error: %s", exc)
