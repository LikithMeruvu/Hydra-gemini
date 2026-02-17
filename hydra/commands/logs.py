"""hydra logs — View request logs."""

from __future__ import annotations

import asyncio

import typer

from hydra.core.constants import MODEL_SHORT_NAMES
from hydra.ui.themes import console

logs_app = typer.Typer(help="View request logs")


@logs_app.callback(invoke_without_command=True)
def logs(
    tail: int = typer.Option(20, "--tail", "-n", help="Number of recent entries"),
    model: str = typer.Option(None, "--model", "-m", help="Filter by model"),
):
    """Show recent request logs."""
    asyncio.run(_show_logs(tail, model))


async def _show_logs(tail: int, model: str | None):
    from hydra.services.stats_service import StatsService

    stats = StatsService()
    entries = await stats.get_recent_logs(count=tail, model=model)

    if not entries:
        console.print("[warning]No logs found.[/warning]")
        return

    console.print(f"[header]📋 Recent Requests[/header] (last {len(entries)})\n")

    for e in entries:
        ts = e.timestamp.strftime("%H:%M:%S")
        model_short = MODEL_SHORT_NAMES.get(e.model, e.model)
        email_short = e.key_email.split("@")[0] + "@" if e.key_email else "?"

        if e.success:
            from hydra.utils.token_counter import format_tokens

            tok = format_tokens(e.tokens_used)
            icon = "🤖" if "pro" in e.model or "flash" in e.model else "⚡"
            console.print(
                f"  [{ts}] {icon} [model]{model_short}[/model] | "
                f"[key]{email_short}[/key] | {tok} tok | {e.latency_ms}ms | [success]✓[/success]"
            )
        else:
            console.print(
                f"  [{ts}] ❌ [model]{model_short}[/model] | "
                f"[key]{email_short}[/key] | [error]{e.error or 'Unknown'}[/error]"
            )
