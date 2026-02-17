"""Rich table builders for CLI output."""

from __future__ import annotations

from rich.table import Table

from hydra.core.constants import MODEL_SHORT_NAMES
from hydra.ui.themes import console


def keys_table(keys_data: list[dict]) -> Table:
    """Build a pretty table of API keys."""
    table = Table(
        title="🔑 API Keys",
        show_header=True,
        header_style="bold bright_cyan",
        border_style="dim",
    )
    table.add_column("Email", style="cyan", min_width=20)
    table.add_column("Models", style="magenta")
    table.add_column("Health", justify="center")
    table.add_column("Status", justify="center")
    table.add_column("Hash", style="dim", max_width=10)

    for k in keys_data:
        health = k.get("health_score", 0)
        health_str = f"{health}" + (" ✓" if health >= 80 else " ⚠" if health >= 50 else " ✗")
        health_style = "green" if health >= 80 else "yellow" if health >= 50 else "red"

        active = k.get("is_active", False)
        status = "🟢 OK" if active else "🔴 OFF"

        models = ", ".join(
            MODEL_SHORT_NAMES.get(m, m) for m in k.get("available_models", [])
        )

        table.add_row(
            k.get("email", "?"),
            models,
            f"[{health_style}]{health_str}[/]",
            status,
            k.get("key_hash", "")[:8] + "…",
        )

    return table


def status_table(keys_with_usage: list[dict]) -> Table:
    """Build a detailed status table with rate-limit info."""
    table = Table(
        title="📊 Key Status",
        show_header=True,
        header_style="bold bright_cyan",
        border_style="dim",
    )
    table.add_column("Email", style="cyan", min_width=15)
    table.add_column("Model", style="magenta")
    table.add_column("RPM", justify="center")
    table.add_column("RPD", justify="center")
    table.add_column("Health", justify="center")
    table.add_column("Status", justify="center")

    for k in keys_with_usage:
        rpm = f"{k.get('rpm_used', 0)}/{k.get('rpm_limit', 0)}"
        rpd = f"{k.get('rpd_used', 0)}/{k.get('rpd_limit', 0)}"
        health = k.get("health_score", 0)
        health_style = "green" if health >= 80 else "yellow" if health >= 50 else "red"

        rpd_pct = (k.get("rpd_used", 0) / max(k.get("rpd_limit", 1), 1)) * 100
        status = "🟢 OK" if rpd_pct < 50 else "🟡 High" if rpd_pct < 100 else "🔴 Max"

        table.add_row(
            k.get("email", "?")[:15] + "…" if len(k.get("email", "")) > 15 else k.get("email", "?"),
            MODEL_SHORT_NAMES.get(k.get("model", ""), k.get("model", "")),
            rpm,
            rpd,
            f"[{health_style}]{health} {'✓' if health >= 80 else '⚠'}[/]",
            status,
        )

    return table
