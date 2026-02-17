"""hydra reset — Reset rate limits and data."""

from __future__ import annotations

import asyncio

import typer

from hydra.ui.panels import success_panel, warning_panel
from hydra.ui.themes import console

reset_app = typer.Typer(help="Reset rate limits and data")


@reset_app.callback(invoke_without_command=True)
def reset(
    rate_limits: bool = typer.Option(False, "--rate-limits", help="Reset only rate limit counters"),
    all_data: bool = typer.Option(False, "--all", help="Reset ALL data (keys, logs, everything)"),
):
    """Reset rate limits or all stored data."""
    if not rate_limits and not all_data:
        console.print("[warning]Specify --rate-limits or --all[/warning]")
        raise typer.Exit(1)

    asyncio.run(_reset(rate_limits, all_data))


async def _reset(rate_limits: bool, all_data: bool):
    from hydra.core.redis_client import get_redis
    from hydra.core.constants import REDIS_KEY_APIKEYS, REDIS_KEY_ACTIVE_KEYS, REDIS_KEY_LOGS, REDIS_KEY_RATELIMIT

    r = await get_redis()

    if all_data:
        confirm = typer.confirm("⚠️  This will delete ALL data (keys, logs, config). Continue?")
        if not confirm:
            console.print("[info]Cancelled.[/info]")
            return
        await r.flushdb()
        success_panel("Reset Complete", "All data has been cleared.\nRun 'hydra setup' to re-initialize.")
        return

    if rate_limits:
        from hydra.services.rate_limiter import RateLimiter

        rl = RateLimiter()
        count = await rl.reset_rpd_all()
        success_panel("Rate Limits Reset", f"Reset {count} rate-limit entries.\nAll RPM/RPD/TPM counters cleared.")
