"""Progress bar helpers."""

from __future__ import annotations

from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from hydra.ui.themes import console


def create_key_progress() -> Progress:
    """Create a progress bar for key validation."""
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=30),
        TaskProgressColumn(),
        console=console,
    )
