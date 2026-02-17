"""Hydra color theme and console singleton."""

from __future__ import annotations

import os
import sys

# Force UTF-8 on Windows to avoid UnicodeEncodeError with Rich
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from rich.console import Console
from rich.theme import Theme

TUI_THEME = Theme({
    "info": "cyan",
    "success": "bold green",
    "warning": "bold yellow",
    "error": "bold red",
    "key": "dim cyan",
    "model": "magenta",
    "number": "bold white",
    "header": "bold bright_cyan",
    "muted": "dim",
})

console = Console(theme=TUI_THEME)
