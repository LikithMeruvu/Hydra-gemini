"""Custom exception hierarchy for Hydra."""

from __future__ import annotations


class TUIError(Exception):
    """Base exception for all Hydra errors."""


class AllKeysExhaustedError(TUIError):
    """Raised when no API key + model combination has remaining capacity."""

    def __init__(self, message: str = "All API keys are exhausted or rate-limited"):
        super().__init__(message)


class RateLimitExceededError(TUIError):
    """Raised when a specific key+model has hit its rate limit."""

    def __init__(self, key_hash: str, model: str, limit_type: str):
        self.key_hash = key_hash
        self.model = model
        self.limit_type = limit_type
        super().__init__(f"Rate limit ({limit_type}) exceeded for key {key_hash[:8]}… on {model}")


class InvalidAPIKeyError(TUIError):
    """Raised when an API key fails validation."""

    def __init__(self, email: str, reason: str = "Invalid API key"):
        self.email = email
        self.reason = reason
        super().__init__(f"Key for {email}: {reason}")


class RedisConnectionError(TUIError):
    """Raised when Redis is unreachable."""

    def __init__(self, url: str = ""):
        self.url = url
        super().__init__(f"Cannot connect to Redis{f' at {url}' if url else ''}")


class GeminiAPIError(TUIError):
    """Raised when the Gemini API returns an error."""

    def __init__(self, status_code: int, message: str, model: str = ""):
        self.status_code = status_code
        self.model = model
        super().__init__(f"Gemini API error {status_code}{f' ({model})' if model else ''}: {message}")
