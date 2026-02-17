"""hydra keys — Manage API keys."""

from __future__ import annotations

import asyncio

import typer

from hydra.ui.panels import success_panel, error_panel
from hydra.ui.tables import keys_table
from hydra.ui.themes import console

keys_app = typer.Typer(help="Manage API keys")


@keys_app.command("list")
def keys_list():
    """List all stored API keys."""
    asyncio.run(_list_keys())


@keys_app.command("add")
def keys_add(
    email: str = typer.Option(..., "--email", "-e", help="Gmail address"),
    key: str = typer.Option(..., "--key", "-k", help="Gemini API key"),
    notes: str = typer.Option("", "--notes", "-n", help="Optional notes"),
):
    """Add a single API key."""
    asyncio.run(_add_key(email, key, notes))


@keys_app.command("remove")
def keys_remove(
    key_hash: str = typer.Argument(..., help="Key hash (first 8+ chars)"),
):
    """Remove an API key by its hash."""
    asyncio.run(_remove_key(key_hash))


@keys_app.command("validate")
def keys_validate():
    """Re-validate all stored keys."""
    asyncio.run(_validate_all())


async def _list_keys():
    from hydra.services.api_key_service import APIKeyService
    from hydra.services.gemini_client import GeminiClient

    key_svc = APIKeyService(GeminiClient())
    all_keys = await key_svc.get_all_keys()

    if not all_keys:
        console.print("[warning]No keys stored. Run 'hydra setup' first.[/warning]")
        return

    data = [
        {
            "key_hash": kh,
            "email": e.email,
            "is_active": e.is_active,
            "health_score": e.health_score,
            "available_models": e.available_models,
        }
        for kh, e in all_keys.items()
    ]
    console.print(keys_table(data))
    console.print(f"\nTotal: [number]{len(data)}[/number] keys")


async def _add_key(email: str, api_key: str, notes: str):
    from hydra.services.api_key_service import APIKeyService
    from hydra.services.gemini_client import GeminiClient
    from hydra.core.redis_client import get_redis

    key_svc = APIKeyService(GeminiClient())

    console.print(f"🔍 Validating key for [cyan]{email}[/cyan]...")
    result = await key_svc.validate_api_key(api_key)

    if not result["valid"]:
        error_panel("Invalid Key", f"{email}: {result['error']}")
        raise typer.Exit(1)

    kh = await key_svc.add_api_key(api_key, email, result["available_models"], notes)

    r = await get_redis()
    await r.hset("_plainkeys", kh, api_key)

    success_panel("Key Added", f"{email}\nModels: {', '.join(result['available_models'])}\nHash: {kh[:8]}…")


async def _remove_key(key_hash: str):
    from hydra.services.api_key_service import APIKeyService
    from hydra.services.gemini_client import GeminiClient
    from hydra.core.redis_client import get_redis

    key_svc = APIKeyService(GeminiClient())

    # Support partial hashes
    all_keys = await key_svc.get_all_keys()
    matches = [kh for kh in all_keys if kh.startswith(key_hash)]

    if not matches:
        error_panel("Not Found", f"No key matching hash '{key_hash}'")
        raise typer.Exit(1)
    if len(matches) > 1:
        error_panel("Ambiguous", f"Multiple keys match '{key_hash}'. Be more specific.")
        raise typer.Exit(1)

    full_hash = matches[0]
    entry = all_keys[full_hash]
    await key_svc.remove_api_key(full_hash)

    r = await get_redis()
    await r.hdel("_plainkeys", full_hash)

    success_panel("Key Removed", f"{entry.email} ({full_hash[:8]}…)")


async def _validate_all():
    from hydra.services.api_key_service import APIKeyService
    from hydra.services.gemini_client import GeminiClient
    from hydra.core.redis_client import get_redis

    key_svc = APIKeyService(GeminiClient())

    all_keys = await key_svc.get_all_keys()
    if not all_keys:
        console.print("[warning]No keys to validate.[/warning]")
        return

    r = await get_redis()
    console.print(f"🔍 Re-validating [number]{len(all_keys)}[/number] keys...")

    for kh, entry in all_keys.items():
        api_key = await r.hget("_plainkeys", kh)
        if not api_key:
            console.print(f"  ⚠ {entry.email}: plaintext key not found (re-add with 'hydra keys add')")
            continue

        result = await key_svc.validate_api_key(api_key)
        status = "[success]✓[/success]" if result["valid"] else "[error]✗[/error]"
        console.print(f"  {status} {entry.email}: {result.get('error', 'OK')}")
