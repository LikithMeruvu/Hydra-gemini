"""POST /v1/embeddings — OpenAI-compatible embeddings endpoint."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

from hydra.core.constants import CAP_EMBEDDING, OPENAI_MODEL_MAP
from hydra.core.exceptions import AllKeysExhaustedError, GeminiAPIError
from hydra.models.schemas import (
    EmbeddingData,
    EmbeddingRequest,
    EmbeddingResponse,
    RequestLogEntry,
    UsageInfo,
)
from hydra.services.gemini_client import GeminiClient
from hydra.core.redis_client import get_redis

logger = logging.getLogger(__name__)

router = APIRouter()


async def _get_raw_key(key_hash: str) -> str | None:
    r = await get_redis()
    return await r.hget("_plainkeys", key_hash)


@router.post("/v1/embeddings")
async def create_embeddings(request: EmbeddingRequest, raw_request: Request):
    """OpenAI-compatible embeddings, routed through Gemini embedding models."""
    from hydra.api.app import router_service, key_service, rate_limiter, stats_service, gemini_client, token_service

    if not router_service or not gemini_client:
        raise HTTPException(503, "Gateway not initialized")

    # Normalize input to list
    texts = [request.input] if isinstance(request.input, str) else request.input

    # Map model name
    preferred_model = OPENAI_MODEL_MAP.get(request.model, request.model)

    try:
        key_hash, model, email, preview = await router_service.select_best_key_and_model(
            preferred_model=preferred_model,
            estimated_tokens=sum(GeminiClient.estimate_tokens(t) for t in texts),
            required_capabilities={CAP_EMBEDDING},
        )

        api_key = await _get_raw_key(key_hash)
        if not api_key:
            raise HTTPException(500, "API key not accessible. Run 'hydra setup' first.")

        result = await gemini_client.embed_content(api_key, model, texts)

        # Record rate limit
        await rate_limiter.record_request(key_hash, model, sum(GeminiClient.estimate_tokens(t) for t in texts))

        # Record health
        await key_service.update_health(key_hash, success=True)

        # Log
        log_entry = RequestLogEntry(
            timestamp=datetime.now(timezone.utc),
            key_hash=key_hash,
            key_email=email,
            model=model,
            tokens_used=sum(GeminiClient.estimate_tokens(t) for t in texts),
            success=True,
            latency_ms=result["latency_ms"],
        )
        await stats_service.log_request(log_entry)

        # Build response
        data = [
            EmbeddingData(index=i, embedding=emb)
            for i, emb in enumerate(result["embeddings"])
        ]

        # Track token usage
        total_toks = sum(GeminiClient.estimate_tokens(t) for t in texts)
        bearer_token = getattr(raw_request.state, "bearer_token", None)
        if bearer_token and token_service:
            await token_service.record_usage(bearer_token, model, total_toks)

        return EmbeddingResponse(
            data=data,
            model=model,
            usage=UsageInfo(
                prompt_tokens=total_toks,
                total_tokens=total_toks,
            ),
        )

    except AllKeysExhaustedError:
        raise HTTPException(429, "All embedding keys are rate-limited")
    except GeminiAPIError as exc:
        raise HTTPException(502, f"Gemini embedding error: {exc}")
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Unexpected error in embeddings")
        raise HTTPException(500, f"Internal error: {exc}")
