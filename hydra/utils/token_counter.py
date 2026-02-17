"""Token estimation utility."""

from __future__ import annotations

from hydra.core.constants import TOKEN_ESTIMATION_BUFFER, TOKEN_ESTIMATION_CHARS_PER_TOKEN


def estimate_tokens(text: str) -> int:
    """Conservative token count from text length."""
    if not text:
        return 0
    return int((len(text) / TOKEN_ESTIMATION_CHARS_PER_TOKEN) * TOKEN_ESTIMATION_BUFFER)


def format_tokens(count: int) -> str:
    """Human-readable token count (e.g., '1.2K', '500')."""
    if count >= 1_000_000:
        return f"{count / 1_000_000:.1f}M"
    if count >= 1_000:
        return f"{count / 1_000:.1f}K"
    return str(count)
