"""Hydra Onboard — The Unified Setup Command."""

import asyncio
import sys
import typer
from pathlib import Path
from hydra.ui.themes import console
from hydra.ui.panels import banner

onboard_app = typer.Typer(help="Unified installer and setup wizard")

@onboard_app.callback(invoke_without_command=True)
def onboard(
    file: str = typer.Option("keys.json", help="Path to keys.json file"),
):
    """
    🚀 One-click setup for Hydra.
    
    1. Checks/Installs Redis
    2. Starts Redis
    3. Runs Setup (Key Validation)
    4. Offers to start Gateway
    """
    banner()
    console.print("[bold cyan]🧙 Hydra Onboard Wizard[/bold cyan]")
    console.print("We will set up everything for you.\n")

    # 1. Redis Manager
    from hydra.services.redis_service import RedisManager
    redis_mgr = RedisManager()

    console.print("[yellow]🔍 Checking Redis status...[/yellow]")
    if redis_mgr.is_running():
        console.print("[green]✅ Redis is already running.[/green]")
    else:
        console.print("[yellow]⚙️ Redis not detected. Attempting to start/install...[/yellow]")
        try:
            # Run async start
            success = asyncio.run(redis_mgr.start())
            if success:
                console.print("[green]✅ Redis started successfully![/green]")
            else:
                console.print("[bold red]❌ Failed to start Redis.[/bold red]")
                console.print("Please install Redis manually or check permissions.")
                raise typer.Exit(code=1)
        except Exception as e:
            console.print(f"[bold red]❌ Error starting Redis: {e}[/bold red]")
            raise typer.Exit(code=1)

    # 2. Check keys.json
    keys_path = Path(file)
    if not keys_path.exists():
        console.print(f"\n[yellow]⚠️ {file} not found![/yellow]")
        create = typer.confirm("Do you want to create a template keys.json?", default=True)
        if create:
            # Create a dummy file
            import json
            template = [
                {
                    "email": "your_email@gmail.com",
                    "api_key": "AIzaSy_PASTE_YOUR_KEY_HERE",
                    "project_id": "project-id-001"
                }
            ]
            keys_path.write_text(json.dumps(template, indent=2))
            console.print(f"[green]✅ Created {file}.[/green]")
            console.print(f"[bold]👉 Please open {file} and add your API keys now.[/bold]")
            
            # Wait for user
            typer.confirm("Press Enter once you have added your keys to the file...", default=True)
        else:
            console.print("[red]Cannot proceed without keys.[/red]")
            raise typer.Exit(1)

    # 3. Run Setup Validation
    console.print("\n[bold cyan]🔑 Validating Keys...[/bold cyan]")
    try:
        # Import setup logic
        from hydra.commands.setup import _run_setup
        asyncio.run(_run_setup(str(keys_path)))
    except Exception as e:
        console.print(f"[red]Setup failed: {e}[/red]")
        # Don't exit, might be partial failure

    # 4. Success & Launch
    console.print("\n[bold green]✅ Onboard Complete![/bold green]")
    start_now = typer.confirm("🚀 Do you want to start the API Gateway now?", default=True)
    
    if start_now:
        # Run gateway
        from hydra.commands.gateway import gateway
        # We invoke the callback function directly
        # Note: gateway() uses typer.Option defaults if not passed, but we should pass defaults manually if needed.
        # However, calling it as a python function requires matching signature.
        # It takes: port, host, reload, expose.
        console.print("[dim]Starting gateway...[/dim]\n")
        gateway(port=8000, host="127.0.0.1", reload=False, expose=False)
    else:
        console.print("👋 OK. Run [bold]hydra gateway[/bold] when you are ready.")
