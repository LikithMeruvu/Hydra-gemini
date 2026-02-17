"""Rich panel / display helpers."""

from __future__ import annotations

from rich.panel import Panel
from rich.text import Text

from hydra.ui.themes import console


def banner() -> None:
    """Print the Hydra startup banner."""
    from hydra.__version__ import __version__

    banner_text = Text()
    banner_text.append("╔════════════════════════════════════════╗\n", style="bright_cyan")
    banner_text.append("║  ", style="bright_cyan")
    banner_text.append("⚡ GeminiHydra", style="bold bright_white")
    banner_text.append(f" v{__version__}", style="dim")
    banner_text.append("     ║\n", style="bright_cyan")
    banner_text.append("║  ", style="bright_cyan")
    banner_text.append("Unlimited Gemini API Gateway", style="cyan")
    banner_text.append("       ║\n", style="bright_cyan")
    banner_text.append("╚════════════════════════════════════════╝", style="bright_cyan")
    console.print(banner_text)


def success_panel(title: str, message: str) -> None:
    """Display a green success panel."""
    console.print(Panel(message, title=f"✅ {title}", border_style="green"))


def error_panel(title: str, message: str) -> None:
    """Display a red error panel."""
    console.print(Panel(message, title=f"❌ {title}", border_style="red"))


def info_panel(title: str, message: str) -> None:
    """Display a cyan info panel."""
    console.print(Panel(message, title=f"ℹ️  {title}", border_style="cyan"))


def warning_panel(title: str, message: str) -> None:
    """Display a yellow warning panel."""
    console.print(Panel(message, title=f"⚠️  {title}", border_style="yellow"))
