"""Miscellaneous helper functions."""

from __future__ import annotations

import hashlib
import socket


def sha256(data: str) -> str:
    """SHA-256 hex digest."""
    return hashlib.sha256(data.encode()).hexdigest()


def get_local_ip() -> str:
    """Get the machine's LAN IP address."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"
