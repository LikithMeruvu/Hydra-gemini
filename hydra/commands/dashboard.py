"""hydra dashboard — Interactive Hydra dashboard (placeholder for Textual-based UI)."""

from __future__ import annotations

import typer

from hydra.ui.themes import console

dashboard_app = typer.Typer(help="Interactive Hydra dashboard")


@dashboard_app.callback(invoke_without_command=True)
def dashboard():
    """Launch the interactive dashboard (coming soon — uses 'hydra status --watch' for now)."""
    console.print("[info]Interactive dashboard is planned for v0.2.0[/info]")
    console.print("For now, use: [bold]hydra status --watch[/bold]")
