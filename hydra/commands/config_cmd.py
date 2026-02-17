"""hydra config — Configuration management."""

from __future__ import annotations

import asyncio
import json

import typer

from hydra.core.constants import MODEL_PRIORITY, REDIS_KEY_CONFIG
from hydra.ui.themes import console

config_app = typer.Typer(help="Configuration management")


@config_app.command("show")
def config_show():
    """Display current configuration."""
    asyncio.run(_show_config())


@config_app.command("set")
def config_set(
    key: str = typer.Argument(..., help="Config key (e.g. retry_attempts)"),
    value: str = typer.Argument(..., help="New value"),
):
    """Set a configuration value."""
    asyncio.run(_set_config(key, value))


@config_app.command("reset")
def config_reset():
    """Reset to default configuration."""
    asyncio.run(_reset_config())


async def _show_config():
    from hydra.core.redis_client import get_redis
    from hydra.core.config import get_settings

    settings = get_settings()
    r = await get_redis()
    stored = await r.hgetall(REDIS_KEY_CONFIG) or {}

    console.print("[header]⚙️  Hydra Configuration[/header]\n")
    console.print(f"  Redis URL:       [dim]{settings.redis_url}[/dim]")
    console.print(f"  Host:            [info]{settings.host}[/info]")
    console.print(f"  Port:            [number]{settings.port}[/number]")
    console.print(f"  Health Weight:   [number]{settings.health_weight}[/number]")
    console.print(f"  Capacity Weight: [number]{settings.capacity_weight}[/number]")
    console.print(f"  Retry Attempts:  [number]{settings.retry_attempts}[/number]")
    console.print(f"  Fallback:        [info]{settings.fallback_enabled}[/info]")
    console.print(f"  Log Level:       [dim]{settings.log_level}[/dim]")

    if stored:
        console.print(f"\n[header]Redis Overrides:[/header]")
        for k, v in stored.items():
            console.print(f"  {k}: {v}")


async def _set_config(key: str, value: str):
    from hydra.core.redis_client import get_redis

    r = await get_redis()
    await r.hset(REDIS_KEY_CONFIG, key, value)
    console.print(f"[success]✓[/success] Set [info]{key}[/info] = {value}")


async def _reset_config():
    from hydra.core.redis_client import get_redis

    r = await get_redis()
    defaults = {
        "model_priority": json.dumps(MODEL_PRIORITY),
        "health_weight": "0.4",
        "capacity_weight": "0.6",
        "retry_attempts": "3",
        "fallback_enabled": "true",
    }
    await r.delete(REDIS_KEY_CONFIG)
    pipe = r.pipeline()
    for k, v in defaults.items():
        pipe.hset(REDIS_KEY_CONFIG, k, v)
    await pipe.execute()
    console.print("[success]✓ Configuration reset to defaults[/success]")
