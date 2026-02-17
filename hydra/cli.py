"""Hydra CLI — main entry point.

Usage:
    hydra setup       Load & validate API keys
    hydra gateway     Start the API gateway
    hydra status      Real-time monitoring
    hydra keys        Manage API keys
    hydra logs        View request logs
    hydra test        Test & benchmark
    hydra config      Configuration
    hydra reset       Reset data
    hydra dashboard   Interactive dashboard
    hydra doctor      System diagnostics
    hydra tokens      Manage API access tokens
"""

from __future__ import annotations

import typer

from hydra.__version__ import __version__

app = typer.Typer(
    name="hydra",
    help="⚡ GeminiHydra — Aggregate free-tier Gemini API keys into one powerful gateway",
    add_completion=False,
    no_args_is_help=True,
    rich_markup_mode="rich",
)


def version_callback(value: bool):
    if value:
        from hydra.ui.themes import console
        console.print(f"Hydra v{__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False, "--version", "-V", callback=version_callback, is_eager=True, help="Show version"
    ),
):
    """GeminiHydra CLI."""
    pass


# Register subcommands
from hydra.commands.setup import setup_app
from hydra.commands.gateway import gateway_app
from hydra.commands.status import status_app
from hydra.commands.keys import keys_app
from hydra.commands.logs import logs_app
from hydra.commands.test_cmd import test_app
from hydra.commands.config_cmd import config_app
from hydra.commands.reset import reset_app
from hydra.commands.dashboard import dashboard_app
from hydra.commands.doctor import doctor_app
from hydra.commands.tokens_cmd import tokens_app
from hydra.commands.onboard import onboard_app

app.add_typer(setup_app, name="setup")
app.add_typer(onboard_app, name="onboard")
app.add_typer(gateway_app, name="gateway")
app.add_typer(status_app, name="status")
app.add_typer(keys_app, name="keys")
app.add_typer(logs_app, name="logs")
app.add_typer(test_app, name="test")
app.add_typer(config_app, name="config")
app.add_typer(reset_app, name="reset")
app.add_typer(dashboard_app, name="dashboard")
app.add_typer(doctor_app, name="doctor")
app.add_typer(tokens_app, name="tokens")


if __name__ == "__main__":
    app()

def run():
    """Entry point for console_scripts."""
    app()
