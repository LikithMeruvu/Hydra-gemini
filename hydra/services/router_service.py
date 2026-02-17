"""Intelligent router — selects the best key+model with proper fallback and exclusion."""

from __future__ import annotations

import logging
from typing import Optional

from hydra.core.constants import (
    IMAGE_MODEL_PRIORITY,
    MODEL_CAPABILITIES,
    MODEL_PRIORITY,
    MODEL_RATE_LIMITS,
    CAP_FUNCTION_CALLING,
    CAP_SEARCH_GROUNDING,
    CAP_CODE_EXECUTION,
    CAP_IMAGE_GENERATION,
    CAP_EMBEDDING,
    CAP_STRUCTURED_OUTPUT,
    CAP_URL_CONTEXT,
    GEMINI_EMBEDDING,
)
from hydra.core.exceptions import AllKeysExhaustedError
from hydra.services.api_key_service import APIKeyService
from hydra.services.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)


class RouterService:
    """Scores and selects the best API key + model, with fallback across ALL options."""

    def __init__(
        self,
        key_service: APIKeyService,
        rate_limiter: RateLimiter,
        health_weight: float = 0.4,
        capacity_weight: float = 0.6,
    ):
        self.keys = key_service
        self.rl = rate_limiter
        self.health_weight = health_weight
        self.capacity_weight = capacity_weight

    async def select_best_key_and_model(
        self,
        preferred_model: Optional[str] = None,
        estimated_tokens: int = 0,
        required_capabilities: Optional[set[str]] = None,
        exclude_pairs: Optional[set[tuple[str, str]]] = None,
        blocked_models: Optional[set[str]] = None,
    ) -> tuple[str, str, str, str]:
        """Pick the best (key_hash, model, email, key_preview).

        - exclude_pairs: specific (key_hash, model) combos that already failed
        - blocked_models: entire models to skip (e.g. model got 429 on 2+ keys)
        """
        models_to_try = self._build_model_order(preferred_model, required_capabilities)
        active_keys = await self.keys.get_active_keys()
        exclude = exclude_pairs or set()
        blocked = blocked_models or set()

        if not active_keys:
            raise AllKeysExhaustedError("No active API keys available")

        fallback_count = 0
        for model in models_to_try:
            # Skip blocked models entirely
            if model in blocked:
                fallback_count += 1
                continue

            # Capability check
            if required_capabilities:
                model_caps = MODEL_CAPABILITIES.get(model, set())
                if not required_capabilities.issubset(model_caps):
                    fallback_count += 1
                    continue

            # Filter keys that support this model AND aren't excluded
            eligible = {
                kh: entry
                for kh, entry in active_keys.items()
                if model in entry.available_models and (kh, model) not in exclude
            }
            if not eligible:
                fallback_count += 1
                continue

            # Score and rank
            scored: list[tuple[float, str]] = []
            for kh, entry in eligible.items():
                can, reason = await self.rl.check_rate_limit(kh, model, estimated_tokens)
                if not can:
                    continue
                usage = await self.rl.get_usage_stats(kh, model)
                score = self._score(entry.health_score, usage)
                scored.append((score, kh))

            if not scored:
                fallback_count += 1
                continue

            scored.sort(reverse=True)
            best_hash = scored[0][1]
            entry = eligible[best_hash]
            logger.info(
                "Routed → %s | %s | score=%.1f | fallbacks=%d | excluded=%d",
                model, entry.email, scored[0][0], fallback_count, len(exclude),
            )
            return best_hash, model, entry.email, entry.api_key_preview

        raise AllKeysExhaustedError(
            f"All keys exhausted across {len(models_to_try)} models "
            f"({len(active_keys)} active, {len(exclude)} excluded)"
        )

    def _build_model_order(
        self,
        preferred: Optional[str],
        required_capabilities: Optional[set[str]] = None,
    ) -> list[str]:
        if required_capabilities and CAP_IMAGE_GENERATION in required_capabilities:
            base = list(IMAGE_MODEL_PRIORITY)
        elif required_capabilities and CAP_EMBEDDING in required_capabilities:
            base = [GEMINI_EMBEDDING]
        else:
            base = list(MODEL_PRIORITY)

        if preferred and preferred in MODEL_RATE_LIMITS:
            return [preferred] + [m for m in base if m != preferred]
        return base

    def _score(self, health: int, usage: dict) -> float:
        rpm_pct = (usage["rpm_used"] / max(usage["rpm_limit"], 1)) * 100
        rpd_pct = (usage["rpd_used"] / max(usage["rpd_limit"], 1)) * 100
        tpm_pct = (usage["tpm_used"] / max(usage["tpm_limit"], 1)) * 100
        capacity_score = 100 - (rpm_pct + rpd_pct + tpm_pct) / 3
        return (health * self.health_weight) + (capacity_score * self.capacity_weight)
