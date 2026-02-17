"""Output formatters."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


def format_duration(seconds: float) -> str:
    """Format seconds as Xh Ym Zs."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    parts = []
    if h:
        parts.append(f"{h}h")
    if m:
        parts.append(f"{m}m")
    parts.append(f"{s}s")
    return " ".join(parts)


def format_time_until_rpd_reset() -> str:
    """Calculate time remaining until midnight Pacific (8:00 AM UTC)."""
    utc_now = datetime.now(timezone.utc)
    # Next 8:00 AM UTC
    today_8am = utc_now.replace(hour=8, minute=0, second=0, microsecond=0)
    if utc_now >= today_8am:
        next_reset = today_8am + timedelta(days=1)
    else:
        next_reset = today_8am
    remaining = (next_reset - utc_now).total_seconds()
    return format_duration(remaining)


def truncate_email(email: str, max_len: int = 20) -> str:
    """Shorten an email for display."""
    if len(email) <= max_len:
        return email
    user, domain = email.split("@", 1)
    return f"{user[:max_len - len(domain) - 3]}…@{domain}"
