"""hydra gateway — Start the Hydra API gateway server."""

from __future__ import annotations

import typer
import uvicorn

from hydra.core.constants import DEFAULT_HOST, DEFAULT_PORT
from hydra.ui.panels import banner
from hydra.ui.themes import console
from hydra.utils.helpers import get_local_ip

gateway_app = typer.Typer(help="Start the API gateway server")


@gateway_app.callback(invoke_without_command=True)
def gateway(
    port: int = typer.Option(DEFAULT_PORT, "--port", "-p", help="Port to listen on"),
    host: str = typer.Option(DEFAULT_HOST, "--host", "-h", help="Host to bind to"),
    reload: bool = typer.Option(False, "--reload", help="Enable auto-reload (dev)"),
    expose: bool = typer.Option(False, "--expose", "-e", help="Expose via Cloudflare tunnel (public HTTPS)"),
):
    """Start the Hydra FastAPI gateway server."""
    banner()
    local_ip = get_local_ip()

    console.print(f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[success]🚀 Hydra Gateway Starting![/success]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📡 Status: [success]ONLINE[/success]
🌐 Local:   [info]http://{host}:{port}[/info]
🌍 Network: [info]http://{local_ip}:{port}[/info]

📋 Endpoints:
   POST   [dim]/v1/chat/completions[/dim]   (streaming supported)
   GET    [dim]/v1/models[/dim]              (IDE model listing)
   POST   [dim]/v1/embeddings[/dim]
   GET    [dim]/health[/dim]
   GET    [dim]/admin/stats[/dim]
   GET    [dim]/admin/keys/list[/dim]
   POST   [dim]/admin/tokens/create[/dim]    (API token management)
   GET    [dim]/admin/tokens/list[/dim]
   DELETE [dim]/admin/tokens/{{id}}[/dim]
""")

    if expose:
        console.print("[warning]🌐 Expose mode: Starting Cloudflare tunnel...[/warning]")
        console.print("[dim]   (Ctrl+C to stop)[/dim]\n")

        # Start tunnel in background after server starts
        import threading

        def _start_tunnel():
            import time
            import requests as req
            time.sleep(4)  # Wait for server to fully start

            # Start tunnel via HTTP to avoid asyncio loop issues
            try:
                # Import and run tunnel in its own clean asyncio loop
                import asyncio
                from hydra.services.tunnel import TunnelService

                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                tunnel = TunnelService()
                url = loop.run_until_complete(tunnel.start(port))
                console.print(f"\n[success]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/success]")
                console.print(f"[success]🌍 PUBLIC URL: {url}[/success]")
                console.print(f"[success]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/success]")

                # Create token via HTTP request to our own API (avoids asyncio conflicts)
                try:
                    resp = req.post(
                        f"http://127.0.0.1:{port}/admin/tokens/create",
                        json={"name": "auto-expose"},
                        timeout=5,
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        console.print(f"\n[warning]🔑 API Token (save this!):[/warning]")
                        console.print(f"   [info]{data['token']}[/info]")
                        console.print(f"\n[dim]   Usage: Authorization: Bearer {data['token'][:20]}...[/dim]")
                        console.print(f"[dim]   Docs:  {url}/docs[/dim]")
                        console.print(f"[dim]   Create more tokens in web UI → 🎫 Tokens tab[/dim]\n")
                    else:
                        console.print(f"[warning]⚠️ Create a token manually in the 🎫 Tokens tab[/warning]")
                except Exception:
                    console.print(f"[warning]⚠️ Create a token manually in the 🎫 Tokens tab[/warning]")

            except Exception as e:
                console.print(f"\n[error]❌ Tunnel failed: {e}[/error]")
                console.print("[dim]   Install cloudflared: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/[/dim]")

        t = threading.Thread(target=_start_tunnel, daemon=True)
        t.start()

    uvicorn.run(
        "hydra.api.app:create_app",
        factory=True,
        host=host,
        port=port,
        reload=reload,
        log_level="info",
    )
