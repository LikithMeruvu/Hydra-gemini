"""API Token Service — create, validate, track, and revoke access tokens.

Tokens are stored in Redis and used for Bearer auth when the gateway
is exposed globally. Each token tracks per-model usage.
"""

from __future__ import annotations

import hashlib
import json
import logging
import secrets
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field

from hydra.core.redis_client import get_redis

logger = logging.getLogger(__name__)

REDIS_KEY_TOKENS = "tui:tokens"  # hash: token_id → TokenEntry JSON


class TokenEntry(BaseModel):
    """Stored representation of an API access token."""

    id: str = ""
    name: str = ""
    token_preview: str = ""  # last 6 chars
    created_at: str = ""
    is_active: bool = True
    # Usage counters per model: {"gemini-2.5-flash": {"requests": 10, "tokens": 5000}}
    usage: dict[str, dict[str, int]] = Field(default_factory=dict)
    total_requests: int = 0
    total_tokens: int = 0


class TokenService:
    """Manages API access tokens in Redis."""

    @staticmethod
    def _hash_token(token: str) -> str:
        """SHA-256 hash of a token (used as Redis key)."""
        return hashlib.sha256(token.encode()).hexdigest()[:16]

    async def create_token(self, name: str = "") -> dict:
        """Generate a new API token. Returns {token, id, name}."""
        r = await get_redis()
        raw_token = f"hydra-{secrets.token_urlsafe(32)}"
        token_id = self._hash_token(raw_token)

        entry = TokenEntry(
            id=token_id,
            name=name or f"token-{token_id[:6]}",
            token_preview=f"...{raw_token[-6:]}",
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        await r.hset(REDIS_KEY_TOKENS, token_id, entry.model_dump_json())
        # Store plaintext for validation
        await r.hset("tui:token_plain", token_id, raw_token)

        logger.info("Created API token '%s' (id=%s)", entry.name, token_id)
        return {"token": raw_token, "id": token_id, "name": entry.name}

    async def validate_token(self, token: str) -> Optional[TokenEntry]:
        """Check if a token is valid and active. Returns TokenEntry or None."""
        r = await get_redis()
        token_id = self._hash_token(token)
        raw = await r.hget(REDIS_KEY_TOKENS, token_id)
        if not raw:
            return None
        entry = TokenEntry.model_validate_json(raw)
        if not entry.is_active:
            return None
        return entry

    async def record_usage(
        self, token: str, model: str, tokens_used: int
    ) -> None:
        """Record API usage for a token."""
        r = await get_redis()
        token_id = self._hash_token(token)
        raw = await r.hget(REDIS_KEY_TOKENS, token_id)
        if not raw:
            return
        entry = TokenEntry.model_validate_json(raw)

        if model not in entry.usage:
            entry.usage[model] = {"requests": 0, "tokens": 0}
        entry.usage[model]["requests"] += 1
        entry.usage[model]["tokens"] += tokens_used
        entry.total_requests += 1
        entry.total_tokens += tokens_used

        await r.hset(REDIS_KEY_TOKENS, token_id, entry.model_dump_json())

    async def list_tokens(self) -> list[dict]:
        """List all tokens (without revealing the actual token)."""
        r = await get_redis()
        raw_all = await r.hgetall(REDIS_KEY_TOKENS)
        tokens = []
        for tid, raw in raw_all.items():
            entry = TokenEntry.model_validate_json(raw)
            tokens.append({
                "id": entry.id,
                "name": entry.name,
                "preview": entry.token_preview,
                "is_active": entry.is_active,
                "created_at": entry.created_at,
                "total_requests": entry.total_requests,
                "total_tokens": entry.total_tokens,
                "usage": entry.usage,
            })
        return tokens

    async def delete_token(self, token_id: str) -> bool:
        """Delete a token by ID. Returns True if found."""
        r = await get_redis()
        removed = await r.hdel(REDIS_KEY_TOKENS, token_id)
        await r.hdel("tui:token_plain", token_id)
        if removed:
            logger.info("Deleted API token id=%s", token_id)
        return removed > 0

    async def has_any_tokens(self) -> bool:
        """Check if any tokens exist (to determine if auth is needed)."""
        r = await get_redis()
        count = await r.hlen(REDIS_KEY_TOKENS)
        return count > 0
