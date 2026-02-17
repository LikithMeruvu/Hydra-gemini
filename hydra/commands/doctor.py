"""hydra doctor — System diagnostics."""

from __future__ import annotations

import asyncio
import platform
import sys

import typer

from hydra.ui.panels import banner
from hydra.ui.themes import console

doctor_app = typer.Typer(help="System diagnostics")


@doctor_app.callback(invoke_without_command=True)
def doctor():
    """Run system diagnostics — check Redis, Python, keys, network."""
    banner()
    asyncio.run(_run_diagnostics())


async def _run_diagnostics():
    from hydra.__version__ import __version__

    console.print("\n[header]🩺 Hydra Doctor — System Diagnostics[/header]\n")

    # Python version
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    py_ok = sys.version_info >= (3, 10)
    _check("Python Version", f"{py_ver} ({platform.platform()})", py_ok)

    # Hydra version
    _check("Hydra Version", __version__, True)

    # Redis
    try:
        from hydra.core.redis_client import get_redis, check_redis_health

        redis_ok = await check_redis_health()
        if redis_ok:
            r = await get_redis()
            info = await r.info("server")
            redis_ver = info.get("redis_version", "unknown")
            _check("Redis Connection", f"v{redis_ver} — Connected ✓", True)
        else:
            _check("Redis Connection", "Cannot connect", False)
    except Exception as exc:
        _check("Redis Connection", f"Error: {exc}", False)

    # API Keys
    try:
        from hydra.services.api_key_service import APIKeyService
        from hydra.services.gemini_client import GeminiClient

        key_svc = APIKeyService(GeminiClient())
        all_keys = await key_svc.get_all_keys()
        active = sum(1 for e in all_keys.values() if e.is_active)
        disabled = len(all_keys) - active
        msg = f"{active} active, {disabled} disabled"
        _check("API Keys", msg, active > 0)
    except Exception as exc:
        _check("API Keys", f"Cannot check: {exc}", False)

    # Network (test Gemini API reachability)
    try:
        import httpx

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get("https://generativelanguage.googleapis.com/")
        _check("Gemini API Reachable", f"HTTP {resp.status_code}", resp.status_code < 500)
    except Exception as exc:
        _check("Gemini API Reachable", f"Error: {exc}", False)

    # Dependencies
    deps = ["typer", "rich", "fastapi", "uvicorn", "redis", "httpx", "pydantic"]
    missing = []
    for dep in deps:
        try:
            __import__(dep)
        except ImportError:
            missing.append(dep)
    if missing:
        _check("Dependencies", f"Missing: {', '.join(missing)}", False)
    else:
        _check("Dependencies", f"All {len(deps)} packages installed", True)

    console.print()


def _check(label: str, detail: str, ok: bool) -> None:
    icon = "[success]✓[/success]" if ok else "[error]✗[/error]"
    console.print(f"  {icon} {label}: {detail}")
