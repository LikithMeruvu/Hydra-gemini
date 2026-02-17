"""hydra status — Real-time monitoring dashboard."""

from __future__ import annotations

import asyncio
import time

import typer

from hydra.core.constants import ALL_MODELS, MODEL_PRIORITY, MODEL_RATE_LIMITS, MODEL_SHORT_NAMES
from hydra.ui.panels import banner
from hydra.ui.tables import status_table
from hydra.ui.themes import console
from hydra.utils.formatters import format_time_until_rpd_reset

status_app = typer.Typer(help="Real-time status monitoring")


@status_app.callback(invoke_without_command=True)
def status(
    watch: bool = typer.Option(False, "--watch", "-w", help="Auto-refresh every 5s"),
):
    """Show current system status and rate-limit usage."""
    asyncio.run(_show_status(watch))


async def _show_status(watch: bool) -> None:
    from hydra.services.api_key_service import APIKeyService
    from hydra.services.rate_limiter import RateLimiter
    from hydra.services.stats_service import StatsService
    from hydra.services.gemini_client import GeminiClient

    key_svc = APIKeyService(GeminiClient())
    rl = RateLimiter()
    stats_svc = StatsService()

    while True:
        if not watch:
            banner()

        console.clear() if watch else None
        console.print("[header]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/header]")
        console.print("[header]📊 Hydra Status Dashboard[/header]")
        console.print("[header]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/header]")

        rpd_reset = format_time_until_rpd_reset()
        console.print(f"Next RPD Reset: [number]{rpd_reset}[/number] (Midnight PT / 8:00 AM UTC)")

        # Today's stats
        try:
            today = await stats_svc.get_today_stats()
            total_req = today["total_requests"]
            success_rate = today["success_rate"]
            console.print(f"\n📈 Today: [number]{total_req:,}[/number] requests | [success]{success_rate}%[/success] success")
        except Exception:
            console.print("\n[warning]⚠  Cannot fetch stats (Redis may be offline)[/warning]")

        # Model usage bars
        try:
            active_keys = await key_svc.get_active_keys()
            console.print(f"\n🔑 Active Keys: [number]{len(active_keys)}[/number]")
            console.print()

            # Per-model summary
            for model in ALL_MODELS:
                short = MODEL_SHORT_NAMES.get(model, model)
                limits = MODEL_RATE_LIMITS[model]
                keys_with_model = [kh for kh, e in active_keys.items() if model in e.available_models]
                total_rpd_limit = len(keys_with_model) * limits["rpd"]

                total_rpd_used = 0
                for kh in keys_with_model:
                    usage = await rl.get_usage_stats(kh, model)
                    total_rpd_used += usage["rpd_used"]

                pct = int((total_rpd_used / max(total_rpd_limit, 1)) * 100)
                bar_len = 10
                filled = int(bar_len * pct / 100)
                bar = "█" * filled + "░" * (bar_len - filled)
                console.print(
                    f"  {short:<18} [{bar}] {pct:>3}%  ({total_rpd_used:,}/{total_rpd_limit:,})"
                )

            # Per-key detail
            rows = []
            for kh, entry in list(active_keys.items())[:10]:
                for model in entry.available_models:
                    usage = await rl.get_usage_stats(kh, model)
                    rows.append({
                        "email": entry.email,
                        "model": model,
                        "health_score": entry.health_score,
                        **usage,
                    })

            if rows:
                console.print()
                console.print(status_table(rows))

        except Exception as exc:
            console.print(f"\n[error]Error loading keys: {exc}[/error]")

        console.print(f"\n🔄 RPM: 60s rolling | RPD: Resets midnight PT | TPM: 60s rolling")

        if not watch:
            break
        console.print(f"\n[muted]Refreshing in 5s... Press Ctrl+C to stop[/muted]")
        await asyncio.sleep(5)
