"""Redis Service — Manages Redis binary download and execution."""

from __future__ import annotations

import asyncio
import logging
import platform
import shutil
import subprocess
import time
import zipfile
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

REDIS_URLS = {
    # Using tporadowski's fork for Windows as it's the de-facto standard for Windows < 10/11 WSL
    "Windows": "https://github.com/tporadowski/redis/releases/download/v5.0.14.1/Redis-x64-5.0.14.1.zip",
    # Linux/Mac usually have redis in package managers, but we can try to find a static build if needed.
    # For now, we assume user might have it or we guide them.
    # But to be "One Click", we should probably try to use system tools or a static bin.
    # For simplicity in this iteration, we focus heavily on the Windows painful experience.
}


def _get_bin_dir() -> Path:
    """Get the Hydra bin directory."""
    d = Path.home() / ".hydra" / "bin"
    d.mkdir(parents=True, exist_ok=True)
    return d


def find_redis() -> Path | None:
    """Find redis-server binary."""
    # 1. Check system PATH
    found = shutil.which("redis-server")
    if found:
        return Path(found)

    # 2. Check Hydra bin dir
    ext = ".exe" if platform.system() == "Windows" else ""
    # In bin dir, it might be in a subdir if unzipped, or direct
    # For Windows zip, it's usually flat files.
    local = _get_bin_dir() / f"redis-server{ext}"
    if local.exists():
        return local
    
    # Check if inside a 'redis' subdir in bin
    local_subdir = _get_bin_dir() / "redis" / f"redis-server{ext}"
    if local_subdir.exists():
        return local_subdir

    return None


async def download_redis() -> Path:
    """Download Redis for Windows (or guide for others)."""
    system = platform.system()
    
    if system != "Windows":
        # On Linux/Mac, it's safer to ask user to use brew/apt
        # But for 'onboard', we can try to return None and let caller handle it?
        # Or raise.
        raise RuntimeError("On Linux/Mac, please install Redis via 'brew install redis' or 'apt install redis-server'.")

    url = REDIS_URLS["Windows"]
    dest_zip = _get_bin_dir() / "redis.zip"
    dest_dir = _get_bin_dir() / "redis"

    if (dest_dir / "redis-server.exe").exists():
        return dest_dir / "redis-server.exe"

    print(f"⬇️ Downloading Redis from {url}...")
    async with httpx.AsyncClient(follow_redirects=True, timeout=120) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        dest_zip.write_bytes(resp.content)

    print("📦 Extracting Redis...")
    with zipfile.ZipFile(dest_zip, 'r') as zip_ref:
        zip_ref.extractall(dest_dir)

    dest_zip.unlink()  # Cleanup zip
    
    binary = dest_dir / "redis-server.exe"
    if not binary.exists():
        raise RuntimeError("Download successful but redis-server.exe not found in extracted files.")

    return binary


class RedisManager:
    """Manages the Redis process."""

    def __init__(self):
        self._process: subprocess.Popen | None = None

    def is_running(self) -> bool:
        """Check if Redis is responsive on default port."""
        # Simple socket check? Or use redis-py?
        # Let's use simple socket to avoid dep issues if possible, 
        # but we have redis-py installed.
        import socket
        try:
            with socket.create_connection(("localhost", 6379), timeout=1):
                return True
        except (socket.timeout, ConnectionRefusedError, OSError):
            return False

    async def start(self) -> bool:
        """Start Redis if not running."""
        if self.is_running():
            return True

        binary = find_redis()
        if not binary:
            try:
                binary = await download_redis()
            except Exception as e:
                print(f"❌ Failed to download Redis: {e}")
                return False

        print(f"🚀 Starting Redis ({binary})...")
        
        # Start in background but keep it alive
        # On Windows, we want to detach or minimize?
        # subprocess.Popen with creationflags can hide it or make it valid.
        
        if platform.system() == "Windows":
            # CREATE_NEW_PROCESS_GROUP = 0x00000200
            # DETACHED_PROCESS = 0x00000008
            # This allows Redis to keep running even if the shell closes or parent dies.
            kwargs["creationflags"] = 0x00000008 | 0x00000200
            kwargs["shell"] = False # Must be False for detached?
            
            # On Windows, we need to hide the window or make it separate.
            # DETACHED_PROCESS makes it run without a console.
            # If user wants to see it, we would use 'start' command, but then we lose control.
            # Let's trust it runs.
        else:
            # On Posix, we can use start_new_session?
            kwargs["start_new_session"] = True

        self._process = subprocess.Popen(
            [str(binary)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            **kwargs
        )

        # Wait for checking
        for _ in range(20):
            if self.is_running():
                return True
            await asyncio.sleep(0.5)
            if self._process.poll() is not None:
                print("❌ Redis process died immediately.")
                return False

        return False

    def stop(self):
        if self._process:
            self._process.terminate()
