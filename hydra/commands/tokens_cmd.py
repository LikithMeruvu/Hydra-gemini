"""hydra tokens — Manage and monitor API access tokens."""

from __future__ import annotations

import asyncio
import time

import typer

from hydra.ui.themes import console

tokens_app = typer.Typer(help="Manage API access tokens")


async def _get_service():
    from hydra.services.token_service import TokenService
    return TokenService()


@tokens_app.callback(invoke_without_command=True)
def tokens_default(ctx: typer.Context):
    """Show token summary. Use subcommands for more."""
    if ctx.invoked_subcommand is None:
        asyncio.run(_show_tokens())


async def _show_tokens():
    svc = await _get_service()
    tokens = await svc.list_tokens()
    if not tokens:
        console.print("[warning]No API tokens found. Create one with:[/warning]")
        console.print("  [info]hydra tokens create --name my-token[/info]")
        return

    console.print(f"\n[bold]🎫 API Tokens ({len(tokens)})[/bold]\n")

    from rich.table import Table

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Name", style="bold")
    table.add_column("ID", style="dim", max_width=10)
    table.add_column("Preview", style="dim")
    table.add_column("Requests", justify="right")
    table.add_column("Tokens Used", justify="right")
    table.add_column("Status")
    table.add_column("Created")

    for t in tokens:
        status = "[green]✅ Active[/green]" if t["is_active"] else "[red]❌ Revoked[/red]"
        reqs = str(t["total_requests"])
        toks = f"{t['total_tokens']:,}" if t["total_tokens"] else "0"
        created = t["created_at"][:10] if t.get("created_at") else "—"
        table.add_row(t["name"], t["id"][:8] + "…", t["preview"], reqs, toks, status, created)

        # Show per-model breakdown if there's usage
        if t.get("usage"):
            for model, stats in t["usage"].items():
                table.add_row(
                    "", "", f"  └─ {model}",
                    str(stats["requests"]), f"{stats['tokens']:,}",
                    "", "",
                )

    console.print(table)


@tokens_app.command()
def create(
    name: str = typer.Option("", "--name", "-n", help="Token name (e.g. cursor-ide, friend-john)"),
):
    """Create a new API access token."""
    result = asyncio.run(_create_token(name))
    console.print(f"\n[success]✅ Token created![/success]")
    console.print(f"   Name:  [bold]{result['name']}[/bold]")
    console.print(f"   ID:    [dim]{result['id']}[/dim]")
    console.print(f"\n[warning]🔑 Token (save this — shown only once!):[/warning]")
    console.print(f"   [bold cyan]{result['token']}[/bold cyan]")
    console.print(f"\n[dim]   Usage: curl -H 'Authorization: Bearer {result['token'][:20]}...' ...[/dim]\n")


async def _create_token(name: str):
    svc = await _get_service()
    return await svc.create_token(name)


@tokens_app.command()
def revoke(
    token_id: str = typer.Argument(help="Token ID (first 8 chars are enough)"),
):
    """Revoke/delete an API token."""
    asyncio.run(_revoke_token(token_id))


async def _revoke_token(token_id: str):
    svc = await _get_service()
    # Try to match partial IDs
    tokens = await svc.list_tokens()
    match = None
    for t in tokens:
        if t["id"].startswith(token_id):
            match = t
            break

    if not match:
        console.print(f"[error]❌ Token '{token_id}' not found[/error]")
        raise typer.Exit(1)

    removed = await svc.delete_token(match["id"])
    if removed:
        console.print(f"[success]✅ Token '{match['name']}' (id={match['id'][:8]}…) revoked[/success]")
    else:
        console.print(f"[error]❌ Failed to revoke token[/error]")


@tokens_app.command()
def watch(
    interval: int = typer.Option(5, "--interval", "-i", help="Refresh interval (seconds)"),
):
    """Watch token usage in real-time (like hydra status --watch)."""
    asyncio.run(_watch_loop(interval))


async def _watch_loop(interval: int):
    console.print("[dim]Press Ctrl+C to stop[/dim]\n")
    svc = await _get_service()
    
    try:
        while True:
            console.clear()
            # Re-use the service/redis connection
            tokens = await svc.list_tokens()
            _print_tokens_table(tokens)
            
            console.print(f"\n[dim]Refreshing in {interval}s... Press Ctrl+C to stop[/dim]")
            await asyncio.sleep(interval)
    except KeyboardInterrupt:
        console.print("\n[dim]Stopped.[/dim]")


def _print_tokens_table(tokens):
    console.print("[bold]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold]")
    console.print("[bold]🎫 API Token Usage Monitor[/bold]")
    console.print("[bold]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold]\n")

    if not tokens:
        console.print("[dim]No tokens created yet.[/dim]")
        return

    from rich.table import Table

    table = Table(show_header=True, header_style="bold cyan", title="Token Usage")
    table.add_column("Name", style="bold", min_width=12)
    table.add_column("Preview")
    table.add_column("Requests", justify="right")
    table.add_column("Tokens Used", justify="right")
    table.add_column("Status")

    grand_requests = 0
    grand_tokens = 0

    for t in tokens:
        status = "[green]Active[/green]" if t["is_active"] else "[red]Revoked[/red]"
        reqs = t["total_requests"]
        toks = t["total_tokens"]
        grand_requests += reqs
        grand_tokens += toks

        table.add_row(
            t["name"], t["preview"],
            str(reqs), f"{toks:,}", status,
        )

        # Per-model breakdown
        if t.get("usage"):
            for model, stats in t["usage"].items():
                table.add_row(
                    "", f"  └─ {model}",
                    str(stats["requests"]), f"{stats['tokens']:,}", "",
                )

    console.print(table)
    console.print(f"\n[bold]📊 Totals:[/bold] {grand_requests} requests | {grand_tokens:,} tokens across {len(tokens)} token(s)")

