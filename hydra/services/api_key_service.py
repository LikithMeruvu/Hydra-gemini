"""API Key service — CRUD, validation, health tracking in Redis."""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime
from typing import Optional

from hydra.core.constants import (
    ALL_MODELS,
    HEALTH_CONSECUTIVE_ERROR_DISABLE,
    HEALTH_SCORE_FAILURE_DELTA,
    HEALTH_SCORE_MAX,
    HEALTH_SCORE_SUCCESS_DELTA,
    MODEL_PRIORITY,
    REDIS_KEY_ACTIVE_KEYS,
    REDIS_KEY_APIKEYS,
)
from hydra.core.redis_client import get_redis
from hydra.models.schemas import APIKeyEntry
from hydra.services.gemini_client import GeminiClient

logger = logging.getLogger(__name__)


def hash_key(api_key: str) -> str:
    """SHA-256 hash of an API key (used as Redis field key)."""
    return hashlib.sha256(api_key.encode()).hexdigest()


class APIKeyService:
    """Manages API key lifecycle in Redis."""

    def __init__(self, gemini_client: Optional[GeminiClient] = None):
        self.gemini = gemini_client or GeminiClient()

    # ── validation ──────────────────────────────────────────────────────────

    async def validate_api_key(self, api_key: str) -> dict:
        """Validate a key and return {valid, available_models, error}."""
        try:
            available = await self.gemini.detect_available_models(api_key, ALL_MODELS)
            if available:
                return {"valid": True, "available_models": available, "error": None}
            return {"valid": False, "available_models": [], "error": "No models accessible"}
        except Exception as exc:
            return {"valid": False, "available_models": [], "error": str(exc)}

    # ── CRUD ────────────────────────────────────────────────────────────────

    async def add_api_key(
        self,
        api_key: str,
        email: str,
        available_models: list[str],
        notes: str = "",
        project_id: str = "",
    ) -> str:
        """Hash, store, and activate an API key. Returns key_hash.

        If the key already exists in Redis, MERGES with the existing entry
        to preserve health scores, usage data, and accumulated model lists.
        """
        r = await get_redis()
        kh = hash_key(api_key)

        # Check for existing entry — preserve health/usage data
        existing_raw = await r.hget(REDIS_KEY_APIKEYS, kh)
        if existing_raw:
            try:
                existing = APIKeyEntry.model_validate_json(existing_raw)
                # Merge: union models, keep health data, update metadata
                merged_models = list(set(existing.available_models) | set(available_models))
                existing.available_models = merged_models
                existing.email = email
                existing.project_id = project_id or existing.project_id
                existing.last_validated = datetime.utcnow()
                existing.api_key_preview = f"...{api_key[-6:]}"
                if notes:
                    existing.notes = notes
                # Re-enable if it was disabled
                existing.is_active = True
                await r.hset(REDIS_KEY_APIKEYS, kh, existing.model_dump_json())
                await r.sadd(REDIS_KEY_ACTIVE_KEYS, kh)
                logger.info(
                    "Merged key %s: %d models (was %d, found %d new)",
                    kh[:8], len(merged_models),
                    len(existing.available_models), len(available_models),
                )
                return kh
            except Exception as exc:
                logger.warning("Failed to parse existing entry for %s, creating new: %s", kh[:8], exc)

        # New entry
        entry = APIKeyEntry(
            email=email,
            api_key_preview=f"...{api_key[-6:]}",
            project_id=project_id,
            available_models=available_models,
            notes=notes,
            last_validated=datetime.utcnow(),
        )
        await r.hset(REDIS_KEY_APIKEYS, kh, entry.model_dump_json())
        await r.sadd(REDIS_KEY_ACTIVE_KEYS, kh)
        return kh

    async def update_models(self, key_hash: str, available_models: list[str]) -> bool:
        """Update the available models for a key (used by background re-detection).

        Replaces the model list entirely (this is intentional — reflects current
        API availability, not a cumulative merge).
        Returns True if the entry was updated.
        """
        r = await get_redis()
        raw = await r.hget(REDIS_KEY_APIKEYS, key_hash)
        if not raw:
            return False

        entry = APIKeyEntry.model_validate_json(raw)
        old_models = set(entry.available_models)
        new_models = set(available_models)

        if old_models != new_models:
            added = new_models - old_models
            removed = old_models - new_models
            if added:
                logger.info("Key %s: new models detected: %s", key_hash[:8], added)
            if removed:
                logger.info("Key %s: models no longer available: %s", key_hash[:8], removed)

            entry.available_models = available_models
            entry.last_validated = datetime.utcnow()
            await r.hset(REDIS_KEY_APIKEYS, key_hash, entry.model_dump_json())
            return True

        return False

    async def remove_api_key(self, key_hash: str) -> bool:
        """Remove a key by its hash. Returns True if it existed."""
        r = await get_redis()
        removed = await r.hdel(REDIS_KEY_APIKEYS, key_hash)
        await r.srem(REDIS_KEY_ACTIVE_KEYS, key_hash)
        return removed > 0

    async def get_all_keys(self) -> dict[str, APIKeyEntry]:
        """Return {key_hash: APIKeyEntry} for every stored key."""
        r = await get_redis()
        raw = await r.hgetall(REDIS_KEY_APIKEYS)
        return {kh: APIKeyEntry.model_validate_json(data) for kh, data in raw.items()}

    async def get_active_keys(self) -> dict[str, APIKeyEntry]:
        """Return only active, non-disabled keys."""
        all_keys = await self.get_all_keys()
        return {kh: entry for kh, entry in all_keys.items() if entry.is_active}

    async def get_active_key_hashes(self) -> set[str]:
        """Fast lookup of active key hashes from the index set."""
        r = await get_redis()
        return await r.smembers(REDIS_KEY_ACTIVE_KEYS)

    async def get_key(self, key_hash: str) -> Optional[APIKeyEntry]:
        """Get a single key entry by hash."""
        r = await get_redis()
        raw = await r.hget(REDIS_KEY_APIKEYS, key_hash)
        if raw:
            return APIKeyEntry.model_validate_json(raw)
        return None

    # ── health scoring ─────────────────────────────────────────────────────

    async def update_health(self, key_hash: str, success: bool) -> None:
        """Adjust health score after a request succeeds or fails."""
        r = await get_redis()
        raw = await r.hget(REDIS_KEY_APIKEYS, key_hash)
        if not raw:
            return

        entry = APIKeyEntry.model_validate_json(raw)

        if success:
            entry.health_score = min(HEALTH_SCORE_MAX, entry.health_score + HEALTH_SCORE_SUCCESS_DELTA)
            entry.consecutive_errors = 0
        else:
            entry.health_score = max(0, entry.health_score + HEALTH_SCORE_FAILURE_DELTA)
            entry.consecutive_errors += 1

            if entry.consecutive_errors >= HEALTH_CONSECUTIVE_ERROR_DISABLE:
                entry.is_active = False
                await r.srem(REDIS_KEY_ACTIVE_KEYS, key_hash)
                logger.warning("Key %s disabled after %d consecutive errors", key_hash[:8], entry.consecutive_errors)

        await r.hset(REDIS_KEY_APIKEYS, key_hash, entry.model_dump_json())

    async def reactivate_key(self, key_hash: str) -> bool:
        """Re-enable a disabled key. Returns True if found."""
        r = await get_redis()
        raw = await r.hget(REDIS_KEY_APIKEYS, key_hash)
        if not raw:
            return False
        entry = APIKeyEntry.model_validate_json(raw)
        entry.is_active = True
        entry.health_score = HEALTH_SCORE_MAX
        entry.consecutive_errors = 0
        await r.hset(REDIS_KEY_APIKEYS, key_hash, entry.model_dump_json())
        await r.sadd(REDIS_KEY_ACTIVE_KEYS, key_hash)
        return True

    async def get_key_count(self) -> int:
        """Number of active keys."""
        r = await get_redis()
        return await r.scard(REDIS_KEY_ACTIVE_KEYS)
