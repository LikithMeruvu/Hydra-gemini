"""Rate limiter — sliding-window RPM/TPM + daily counter RPD, stored in Redis."""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from hydra.core.constants import (
    MODEL_RATE_LIMITS,
    REDIS_KEY_RATELIMIT,
    TTL_RATE_LIMIT,
)
from hydra.core.redis_client import get_redis

logger = logging.getLogger(__name__)

# Pacific Time is UTC-8 (ignoring DST for simplicity)
_PT_OFFSET = timedelta(hours=-8)


def _now_ts() -> float:
    return time.time()


def _today_pacific() -> str:
    """Return current date in Pacific Time as YYYY-MM-DD."""
    utc_now = datetime.now(timezone.utc)
    pt_now = utc_now + _PT_OFFSET
    return pt_now.strftime("%Y-%m-%d")


class RateLimiter:
    """Per-key, per-model rate limit tracker backed by Redis hashes."""

    def _rkey(self, key_hash: str, model: str) -> str:
        return f"{REDIS_KEY_RATELIMIT}:{key_hash}:{model}"

    # ── check ──────────────────────────────────────────────────────────────

    async def check_rate_limit(
        self,
        key_hash: str,
        model: str,
        estimated_tokens: int = 0,
    ) -> tuple[bool, Optional[str]]:
        """Return (can_proceed, reason_if_blocked)."""
        limits = MODEL_RATE_LIMITS.get(model)
        if not limits:
            return False, f"Unknown model {model}"

        r = await get_redis()
        rkey = self._rkey(key_hash, model)
        now = _now_ts()
        window_start = now - 60

        # Fetch all fields at once
        raw = await r.hgetall(rkey)

        # ── RPM check ──
        requests_raw = raw.get("requests", "[]")
        try:
            requests: list[float] = json.loads(requests_raw)
        except json.JSONDecodeError:
            requests = []
        recent = [ts for ts in requests if ts > window_start]
        if len(recent) >= limits["rpm"]:
            return False, f"RPM limit ({limits['rpm']}) reached"

        # ── RPD check ──
        rpd_count = int(raw.get("rpd_count", 0))
        last_reset = raw.get("last_rpd_reset", "")
        today = _today_pacific()
        if last_reset != today:
            rpd_count = 0  # will reset on record
        if rpd_count >= limits["rpd"]:
            return False, f"RPD limit ({limits['rpd']}) reached"

        # ── TPM check ──
        tokens_raw = raw.get("tokens", "[]")
        try:
            token_entries: list[dict] = json.loads(tokens_raw)
        except json.JSONDecodeError:
            token_entries = []
        recent_tokens = sum(e["count"] for e in token_entries if e["ts"] > window_start)
        if recent_tokens + estimated_tokens > limits["tpm"]:
            return False, f"TPM limit ({limits['tpm']}) would be exceeded"

        return True, None

    # ── record ─────────────────────────────────────────────────────────────

    async def record_request(
        self,
        key_hash: str,
        model: str,
        tokens_used: int,
    ) -> None:
        """Record a successful request for rate limit accounting."""
        r = await get_redis()
        rkey = self._rkey(key_hash, model)
        now = _now_ts()
        today = _today_pacific()

        raw = await r.hgetall(rkey)

        # RPM timestamps
        try:
            requests: list[float] = json.loads(raw.get("requests", "[]"))
        except json.JSONDecodeError:
            requests = []
        requests.append(now)

        # Token entries
        try:
            token_entries: list[dict] = json.loads(raw.get("tokens", "[]"))
        except json.JSONDecodeError:
            token_entries = []
        token_entries.append({"ts": now, "count": tokens_used})

        # RPD
        last_reset = raw.get("last_rpd_reset", "")
        rpd_count = int(raw.get("rpd_count", 0))
        if last_reset != today:
            rpd_count = 0  # new day
        rpd_count += 1

        pipe = r.pipeline()
        pipe.hset(rkey, "requests", json.dumps(requests))
        pipe.hset(rkey, "tokens", json.dumps(token_entries))
        pipe.hset(rkey, "rpd_count", str(rpd_count))
        pipe.hset(rkey, "last_rpd_reset", today)
        pipe.hset(rkey, "rpm_limit", str(MODEL_RATE_LIMITS.get(model, {}).get("rpm", 0)))
        pipe.hset(rkey, "rpd_limit", str(MODEL_RATE_LIMITS.get(model, {}).get("rpd", 0)))
        pipe.hset(rkey, "tpm_limit", str(MODEL_RATE_LIMITS.get(model, {}).get("tpm", 0)))
        pipe.expire(rkey, TTL_RATE_LIMIT)
        await pipe.execute()

    # ── cleanup ────────────────────────────────────────────────────────────

    async def cleanup_old_data(self, key_hash: str, model: str) -> None:
        """Remove timestamps older than 60 s from the sliding windows."""
        r = await get_redis()
        rkey = self._rkey(key_hash, model)
        now = _now_ts()
        cutoff = now - 60

        raw = await r.hgetall(rkey)
        if not raw:
            return

        try:
            requests: list[float] = json.loads(raw.get("requests", "[]"))
        except json.JSONDecodeError:
            requests = []
        try:
            token_entries: list[dict] = json.loads(raw.get("tokens", "[]"))
        except json.JSONDecodeError:
            token_entries = []

        requests = [ts for ts in requests if ts > cutoff]
        token_entries = [e for e in token_entries if e["ts"] > cutoff]

        pipe = r.pipeline()
        pipe.hset(rkey, "requests", json.dumps(requests))
        pipe.hset(rkey, "tokens", json.dumps(token_entries))
        await pipe.execute()

    # ── stats ──────────────────────────────────────────────────────────────

    async def get_usage_stats(self, key_hash: str, model: str) -> dict:
        """Return current usage vs. limits for a key+model pair."""
        r = await get_redis()
        rkey = self._rkey(key_hash, model)
        now = _now_ts()
        window_start = now - 60

        raw = await r.hgetall(rkey)
        limits = MODEL_RATE_LIMITS.get(model, {"rpm": 0, "rpd": 0, "tpm": 0})

        try:
            requests: list[float] = json.loads(raw.get("requests", "[]"))
        except json.JSONDecodeError:
            requests = []
        try:
            token_entries: list[dict] = json.loads(raw.get("tokens", "[]"))
        except json.JSONDecodeError:
            token_entries = []

        rpm_used = len([ts for ts in requests if ts > window_start])
        tpm_used = sum(e["count"] for e in token_entries if e["ts"] > window_start)

        today = _today_pacific()
        last_reset = raw.get("last_rpd_reset", "")
        rpd_count = int(raw.get("rpd_count", 0)) if last_reset == today else 0

        return {
            "rpm_used": rpm_used,
            "rpm_limit": limits["rpm"],
            "rpd_used": rpd_count,
            "rpd_limit": limits["rpd"],
            "tpm_used": tpm_used,
            "tpm_limit": limits["tpm"],
        }

    async def reset_rpd_all(self) -> int:
        """Reset RPD counters for all keys. Returns count of keys reset."""
        r = await get_redis()
        count = 0
        cursor = "0"
        while True:
            cursor, keys = await r.scan(cursor=cursor, match=f"{REDIS_KEY_RATELIMIT}:*", count=100)
            for rkey in keys:
                await r.hset(rkey, "rpd_count", "0")
                count += 1
            if cursor == "0":
                break
        return count
