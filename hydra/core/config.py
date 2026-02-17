"""Application settings loaded from env vars / .env file.

Uses a plain dataclass to avoid pydantic-settings version issues.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


def _load_dotenv() -> None:
    """Load .env file if present (simple implementation, no dependency)."""
    for env_path in (Path(".env"), Path(__file__).resolve().parents[2] / ".env"):
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key, value = key.strip(), value.strip().strip('"').strip("'")
                os.environ.setdefault(key, value)
            break


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


def _env_int(name: str, default: int) -> int:
    return int(os.environ.get(name, str(default)))


def _env_float(name: str, default: float) -> float:
    return float(os.environ.get(name, str(default)))


def _env_bool(name: str, default: bool) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return val.lower() in ("1", "true", "yes")


@dataclass
class Settings:
    """Hydra configuration — env vars take precedence, then .env, then defaults."""

    # Redis
    redis_url: str = ""
    # Gateway server
    host: str = "127.0.0.1"
    port: int = 8000
    # Router
    health_weight: float = 0.4
    capacity_weight: float = 0.6
    retry_attempts: int = 3
    fallback_enabled: bool = True
    # Paths
    config_dir: Path = field(default_factory=lambda: Path.home() / ".tui")
    # Logging
    log_level: str = "INFO"
    # Optional ngrok
    ngrok_token: Optional[str] = None

    def __post_init__(self) -> None:
        _load_dotenv()
        self.redis_url = _env("REDIS_URL", "redis://localhost:6379/0")
        self.host = _env("TUI_HOST", self.host)
        self.port = _env_int("TUI_PORT", self.port)
        self.health_weight = _env_float("TUI_HEALTH_WEIGHT", self.health_weight)
        self.capacity_weight = _env_float("TUI_CAPACITY_WEIGHT", self.capacity_weight)
        self.retry_attempts = _env_int("TUI_RETRY_ATTEMPTS", self.retry_attempts)
        self.fallback_enabled = _env_bool("TUI_FALLBACK_ENABLED", self.fallback_enabled)
        self.log_level = _env("TUI_LOG_LEVEL", self.log_level)
        self.ngrok_token = os.environ.get("NGROK_AUTH_TOKEN")
        cfg = _env("TUI_CONFIG_DIR", "")
        if cfg:
            self.config_dir = Path(cfg)


# Singleton
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Return the global settings singleton."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
