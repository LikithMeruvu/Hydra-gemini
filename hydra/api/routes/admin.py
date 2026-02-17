"""Admin API routes — key management and stats."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/admin", tags=["admin"])


class AddKeyRequest(BaseModel):
    email: str
    api_key: str
    notes: str = ""


@router.post("/keys/add")
async def add_key(req: AddKeyRequest):
    """Add and validate a new API key."""
    from hydra.api.app import key_service, gemini_client
    from hydra.services.api_key_service import hash_key
    from hydra.core.redis_client import get_redis

    if not key_service:
        raise HTTPException(503, "Gateway not initialized")

    result = await key_service.validate_api_key(req.api_key)
    if not result["valid"]:
        raise HTTPException(400, f"Invalid key: {result['error']}")

    key_hash = await key_service.add_api_key(
        req.api_key, req.email, result["available_models"], req.notes
    )

    # Store plaintext key for gateway use
    r = await get_redis()
    await r.hset("_plainkeys", key_hash, req.api_key)

    return {
        "status": "added",
        "key_hash": key_hash,
        "email": req.email,
        "available_models": result["available_models"],
    }


@router.get("/keys/list")
async def list_keys():
    """List all stored API keys (without revealing the actual key)."""
    from hydra.api.app import key_service

    if not key_service:
        raise HTTPException(503, "Gateway not initialized")

    all_keys = await key_service.get_all_keys()
    return {
        "total": len(all_keys),
        "keys": [
            {
                "key_hash": kh,
                "email": entry.email,
                "preview": entry.api_key_preview,
                "is_active": entry.is_active,
                "health_score": entry.health_score,
                "available_models": entry.available_models,
                "created_at": entry.created_at.isoformat(),
            }
            for kh, entry in all_keys.items()
        ],
    }


@router.delete("/keys/remove/{key_hash}")
async def remove_key(key_hash: str):
    """Remove an API key by its hash."""
    from hydra.api.app import key_service
    from hydra.core.redis_client import get_redis

    if not key_service:
        raise HTTPException(503, "Gateway not initialized")

    removed = await key_service.remove_api_key(key_hash)
    if not removed:
        raise HTTPException(404, "Key not found")

    # Also remove plaintext
    r = await get_redis()
    await r.hdel("_plainkeys", key_hash)

    return {"status": "removed", "key_hash": key_hash}


@router.get("/stats")
async def get_stats():
    """Get today's usage statistics."""
    from hydra.api.app import stats_service, key_service

    if not stats_service or not key_service:
        raise HTTPException(503, "Gateway not initialized")

    today = await stats_service.get_today_stats()
    key_count = await key_service.get_key_count()

    return {
        "active_keys": key_count,
        **today,
    }


@router.get("/stats/keys/{key_hash}")
async def get_key_stats(key_hash: str):
    """Get detailed rate-limit usage for a specific key."""
    from hydra.api.app import key_service, rate_limiter
    from hydra.core.constants import MODEL_PRIORITY

    if not key_service or not rate_limiter:
        raise HTTPException(503, "Gateway not initialized")

    entry = await key_service.get_key(key_hash)
    if not entry:
        raise HTTPException(404, "Key not found")

    model_stats = {}
    for model in entry.available_models:
        model_stats[model] = await rate_limiter.get_usage_stats(key_hash, model)

    return {
        "email": entry.email,
        "health_score": entry.health_score,
        "is_active": entry.is_active,
        "models": model_stats,
    }
