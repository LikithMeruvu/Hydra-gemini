"""hydra test — Test and benchmark API keys."""

from __future__ import annotations

import asyncio
import time

import typer

from hydra.core.constants import MODEL_PRIORITY, MODEL_SHORT_NAMES
from hydra.ui.panels import banner
from hydra.ui.themes import console

test_app = typer.Typer(help="Test & benchmark API keys")


@test_app.callback(invoke_without_command=True)
def test_cmd():
    """Benchmark all keys and models. Shows latency and success rate."""
    banner()
    asyncio.run(_run_tests())


async def _run_tests():
    from hydra.services.api_key_service import APIKeyService
    from hydra.services.gemini_client import GeminiClient
    from hydra.core.redis_client import get_redis
    from rich.table import Table

    gemini = GeminiClient()
    key_svc = APIKeyService(gemini)

    all_keys = await key_svc.get_all_keys()
    if not all_keys:
        console.print("[warning]No keys found. Run 'hydra setup' first.[/warning]")
        return

    r = await get_redis()
    console.print(f"\n🧪 Testing [number]{len(all_keys)}[/number] keys across [number]{len(MODEL_PRIORITY)}[/number] models...\n")

    table = Table(
        title="🏁 Benchmark Results",
        show_header=True,
        header_style="bold bright_cyan",
        border_style="dim",
    )
    table.add_column("Email", style="cyan", min_width=20)
    table.add_column("Model", style="magenta")
    table.add_column("Status", justify="center")
    table.add_column("Latency", justify="right")

    for kh, entry in all_keys.items():
        api_key = await r.hget("_plainkeys", kh)
        if not api_key:
            for model in MODEL_PRIORITY:
                table.add_row(entry.email, MODEL_SHORT_NAMES[model], "[warning]⚠ No key[/warning]", "-")
            continue

        for model in MODEL_PRIORITY:
            t0 = time.perf_counter()
            ok = await gemini.test_api_key(api_key, model)
            elapsed = int((time.perf_counter() - t0) * 1000)

            if ok:
                table.add_row(
                    entry.email,
                    MODEL_SHORT_NAMES[model],
                    "[success]✓ Pass[/success]",
                    f"{elapsed}ms",
                )
            else:
                table.add_row(
                    entry.email,
                    MODEL_SHORT_NAMES[model],
                    "[error]✗ Fail[/error]",
                    f"{elapsed}ms",
                )

    console.print(table)
