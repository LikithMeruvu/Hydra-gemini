"""hydra setup — Load, validate, and store API keys from a JSON file."""

from __future__ import annotations

import asyncio
from typing import Optional

import typer

from hydra.ui.themes import console
from hydra.ui.panels import banner, success_panel, error_panel
from hydra.ui.progress import create_key_progress
from hydra.utils.validators import validate_keys_json
from hydra.core.constants import MODEL_RATE_LIMITS, MODEL_SHORT_NAMES

setup_app = typer.Typer(help="Setup & validate API keys")


@setup_app.callback(invoke_without_command=True)
def setup(
    file: str = typer.Option("keys.json", "--file", "-f", help="Path to JSON file with API keys"),
):
    """Load API keys from a JSON file and validate them with Gemini."""
    banner()
    asyncio.run(_run_setup(file))


async def _run_setup(file: str) -> None:
    # 1. Parse JSON
    try:
        keys = validate_keys_json(file)
    except ValueError as exc:
        error_panel("Invalid Keys File", str(exc))
        raise typer.Exit(1)

    console.print(f"\n🔍 Validating [number]{len(keys)}[/number] API keys...\n")

    # 2. Validate each key
    from hydra.services.gemini_client import GeminiClient
    from hydra.services.api_key_service import APIKeyService, hash_key
    from hydra.core.redis_client import get_redis

    gemini = GeminiClient()
    key_svc = APIKeyService(gemini)

    results: list[dict] = []
    valid_count = 0
    failed: list[dict] = []

    progress = create_key_progress()
    with progress:
        task = progress.add_task("Validating keys", total=len(keys))

        for entry in keys:
            email = entry["email"]
            api_key = entry["api_key"]
            project_id = entry.get("project_id", "")

            result = await key_svc.validate_api_key(api_key)
            if result["valid"]:
                kh = await key_svc.add_api_key(
                    api_key, email, result["available_models"],
                    project_id=project_id,
                )

                # Store plaintext key for gateway use
                r = await get_redis()
                await r.hset("_plainkeys", kh, api_key)

                valid_count += 1
                results.append({
                    "email": email,
                    "project_id": project_id,
                    "models": result["available_models"],
                    "key_hash": kh,
                })
            else:
                failed.append({"email": email, "error": result["error"]})

            progress.advance(task)

    # 3. Display results
    console.print()

    if valid_count:
        console.print(f"[success]✅ {valid_count} keys valid[/success]")
    if failed:
        console.print(f"[error]❌ {len(failed)} keys failed:[/error]")
        for f in failed:
            console.print(f"   • [dim]{f['email']}[/dim]: {f['error']}")

    if valid_count:
        console.print("\n🔍 Model Detection Results:")
        for r in results:
            model_names = ", ".join(MODEL_SHORT_NAMES.get(m, m) for m in r["models"])
            proj = f" [{r['project_id']}]" if r["project_id"] else ""
            console.print(
                f"   ✓ [cyan]{r['email']}[/cyan]{proj}: "
                f"{len(r['models'])} models ({model_names})"
            )

        # Unique projects
        unique_projects = len({r["project_id"] for r in results if r["project_id"]})
        if unique_projects:
            console.print(f"\n🏗️  Unique Projects: [number]{unique_projects}[/number]")

        # Capacity summary
        console.print("\n[header]✨ Setup Complete![/header]")
        console.print("━" * 40)
        console.print(f"Total Keys: [number]{valid_count}[/number] active")
        console.print("Daily Capacity:")
        for model, limits in MODEL_RATE_LIMITS.items():
            short = MODEL_SHORT_NAMES.get(model, model)
            count = sum(1 for r in results if model in r["models"])
            total_rpd = count * limits["rpd"]
            console.print(f"  • {short}: ~[number]{total_rpd:,}[/number] requests")

        total_daily = sum(
            sum(1 for r in results if m in r["models"]) * l["rpd"]
            for m, l in MODEL_RATE_LIMITS.items()
        )
        console.print(f"Total: ~[number]{total_daily:,}[/number] requests/day")
        console.print(f"\nNext: [info]hydra gateway[/info]")
    else:
        error_panel("Setup Failed", "No valid API keys found")
        raise typer.Exit(1)
