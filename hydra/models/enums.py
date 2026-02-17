"""Enumerations used across Hydra."""

from __future__ import annotations

from enum import Enum


class GeminiModel(str, Enum):
    """Supported Gemini models on the free tier."""

    GEMINI_3_FLASH = "gemini-3-flash-preview"
    GEMINI_25_PRO = "gemini-2.5-pro"
    GEMINI_25_FLASH = "gemini-2.5-flash"
    GEMINI_25_FLASH_LITE = "gemini-2.5-flash-lite"


class KeyStatus(str, Enum):
    """Health status of an API key."""

    OK = "ok"
    HIGH_USAGE = "high_usage"
    MAX = "max"
    DISABLED = "disabled"
    UNKNOWN = "unknown"
