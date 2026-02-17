"""Cloudflare Tunnel service — exposes local Hydra gateway globally via HTTPS.

Uses cloudflared (free, no account needed) to create a temporary tunnel.
Auto-downloads the binary if not present.
"""

from __future__ import annotations

import asyncio
import logging
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

CLOUDFLARED_URLS = {
    "Windows": "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe",
    "Linux": "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64",
    "Darwin": "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-darwin-amd64.tgz",
}


def _get_bin_dir() -> Path:
    """Get the Hydra bin directory for storing cloudflared."""
    d = Path.home() / ".hydra" / "bin"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _find_cloudflared() -> Path | None:
    """Find cloudflared binary."""
    # Check system PATH first
    found = shutil.which("cloudflared")
    if found:
        return Path(found)
    # Check Hydra bin dir
    ext = ".exe" if platform.system() == "Windows" else ""
    local = _get_bin_dir() / f"cloudflared{ext}"
    if local.exists():
        return local
    return None


async def download_cloudflared() -> Path:
    """Download cloudflared binary for the current platform."""
    system = platform.system()
    url = CLOUDFLARED_URLS.get(system)
    if not url:
        raise RuntimeError(f"Unsupported platform: {system}")

    ext = ".exe" if system == "Windows" else ""
    dest = _get_bin_dir() / f"cloudflared{ext}"

    if dest.exists():
        return dest

    logger.info("Downloading cloudflared from %s ...", url)

    import httpx
    async with httpx.AsyncClient(follow_redirects=True, timeout=60) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        dest.write_bytes(resp.content)

    if system != "Windows":
        dest.chmod(0o755)

    logger.info("cloudflared downloaded to %s", dest)
    return dest


class TunnelService:
    """Manages a cloudflared tunnel to expose the local gateway."""

    def __init__(self):
        self._process: subprocess.Popen | None = None
        self._public_url: str | None = None

    @property
    def public_url(self) -> str | None:
        return self._public_url

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    async def start(self, port: int = 8000) -> str:
        """Start cloudflared tunnel. Returns the public URL."""
        binary = _find_cloudflared()
        if not binary:
            binary = await download_cloudflared()

        logger.info("Starting cloudflared tunnel on port %d ...", port)

        self._process = subprocess.Popen(
            [
                str(binary),
                "tunnel",
                "--url", f"http://127.0.0.1:{port}",
                "--no-autoupdate",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        # Wait for URL to appear in stderr output
        url = await self._wait_for_url(timeout=30)
        self._public_url = url
        logger.info("Tunnel active: %s", url)
        return url

    async def _wait_for_url(self, timeout: int = 30) -> str:
        """Parse cloudflared output to find the public URL."""
        import asyncio

        url_pattern = re.compile(r"(https://[a-z0-9\-]+\.trycloudflare\.com)")

            if self._process.poll() is not None:
                # Process died — read any output
                if self._process and self._process.stderr:
                    err = self._process.stderr.read()
                    raise RuntimeError(f"cloudflared exited: {err[:300]}")
                raise RuntimeError("cloudflared process not running")

            # Parse line by line
            if self._process.stderr:
                line = self._process.stderr.readline()
                if line:
                    # logger.info(f"Tunnel Log: {line.strip()}") # Debug
                    match = url_pattern.search(line)
                    if match:
                        return match.group(1)
            
            await asyncio.sleep(0.1)

        raise RuntimeError("Timed out waiting for cloudflared URL")

    async def stop(self):
        """Stop the tunnel."""
        if self._process:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
            self._process = None
            self._public_url = None
            logger.info("Tunnel stopped")
