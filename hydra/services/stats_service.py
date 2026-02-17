"""Stats service — log requests and compute aggregates from Redis."""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone

from hydra.core.constants import REDIS_KEY_LOGS, REDIS_KEY_STATS_HOURLY, TTL_LOGS, TTL_STATS_HOURLY
from hydra.core.redis_client import get_redis
from hydra.models.schemas import RequestLogEntry

logger = logging.getLogger(__name__)


class StatsService:
    """Records request logs to a Redis sorted set and computes aggregates."""

    # ── logging ─────────────────────────────────────────────────────────────

    async def log_request(self, entry: RequestLogEntry) -> None:
        """Append a request log entry to the sorted set."""
        r = await get_redis()
        score = entry.timestamp.timestamp()
        await r.zadd(REDIS_KEY_LOGS, {entry.model_dump_json(): score})

        # Update hourly aggregate
        hour_key = f"{REDIS_KEY_STATS_HOURLY}:{entry.timestamp.strftime('%Y-%m-%d-%H')}"
        pipe = r.pipeline()
        pipe.hincrby(hour_key, "total_requests", 1)
        if entry.success:
            pipe.hincrby(hour_key, "successful", 1)
        else:
            pipe.hincrby(hour_key, "failed", 1)
        pipe.hincrby(hour_key, "tokens_used", entry.tokens_used)
        pipe.expire(hour_key, TTL_STATS_HOURLY)
        await pipe.execute()

        # Update model distribution in the hourly hash
        dist_raw = await r.hget(hour_key, "model_distribution") or "{}"
        try:
            dist = json.loads(dist_raw)
        except json.JSONDecodeError:
            dist = {}
        dist[entry.model] = dist.get(entry.model, 0) + 1
        await r.hset(hour_key, "model_distribution", json.dumps(dist))

    # ── queries ─────────────────────────────────────────────────────────────

    async def get_recent_logs(
        self,
        count: int = 50,
        model: str | None = None,
    ) -> list[RequestLogEntry]:
        """Return the most recent log entries, optionally filtered by model."""
        r = await get_redis()
        raw_entries = await r.zrevrange(REDIS_KEY_LOGS, 0, count * 2 - 1)
        logs = []
        for raw in raw_entries:
            try:
                entry = RequestLogEntry.model_validate_json(raw)
                if model and entry.model != model:
                    continue
                logs.append(entry)
                if len(logs) >= count:
                    break
            except Exception:
                continue
        return logs

    async def get_today_stats(self) -> dict:
        """Aggregate stats for the current UTC day."""
        r = await get_redis()
        now = datetime.now(timezone.utc)
        total = {"total_requests": 0, "successful": 0, "failed": 0, "tokens_used": 0, "model_distribution": {}}

        for hour in range(24):
            hkey = f"{REDIS_KEY_STATS_HOURLY}:{now.strftime('%Y-%m-%d')}-{hour:02d}"
            raw = await r.hgetall(hkey)
            if not raw:
                continue
            total["total_requests"] += int(raw.get("total_requests", 0))
            total["successful"] += int(raw.get("successful", 0))
            total["failed"] += int(raw.get("failed", 0))
            total["tokens_used"] += int(raw.get("tokens_used", 0))
            try:
                dist = json.loads(raw.get("model_distribution", "{}"))
                for m, c in dist.items():
                    total["model_distribution"][m] = total["model_distribution"].get(m, 0) + c
            except json.JSONDecodeError:
                pass

        t = total["total_requests"]
        total["success_rate"] = round((total["successful"] / t) * 100, 1) if t else 0
        return total

    async def cleanup_old_logs(self) -> int:
        """Remove log entries older than 7 days. Returns count removed."""
        r = await get_redis()
        cutoff = time.time() - TTL_LOGS
        removed = await r.zremrangebyscore(REDIS_KEY_LOGS, "-inf", cutoff)
        return removed
