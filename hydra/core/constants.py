"""Constants for Hydra — model definitions, rate limits, Redis keys, defaults."""

from __future__ import annotations

# ── Gemini model identifiers (FREE TIER ONLY) ──────────────────────────────
# ── Gemini model identifiers (FREE TIER ONLY) ──────────────────────────────
# Verified free-tier availability as of Feb 2026
GEMINI_3_FLASH = "gemini-3-flash-preview"     # Free for dev
GEMINI_25_PRO = "gemini-2.5-pro"               # Free, 5 RPM / 100 RPD (sunset June 2026)
GEMINI_25_FLASH = "gemini-2.5-flash"           # Free, best balance
GEMINI_25_FLASH_LITE = "gemini-2.5-flash-lite" # Free, highest throughput
GEMINI_25_FLASH_IMAGE = "gemini-2.5-flash-image"  # Free, image generation (reduced quotas)
GEMINI_EMBEDDING = "gemini-embedding-001"      # Free

# NOTE: gemini-3-pro-preview and gemini-3-pro-image-preview are PAID ONLY
# They return 429 "quota exceeded" on free-tier keys.

# Default text model priority (smartest → most economical)
# Router tries top-to-bottom, falling back through the list
MODEL_PRIORITY: list[str] = [
    GEMINI_25_PRO,          # Smartest free-tier model
    GEMINI_3_FLASH,         # Fast, free for dev
    GEMINI_25_FLASH,        # Best throughput/quality balance
    GEMINI_25_FLASH_LITE,   # Highest free-tier limits (15 RPM, 1000 RPD)
]

# Image generation model priority
IMAGE_MODEL_PRIORITY: list[str] = [
    GEMINI_25_FLASH_IMAGE,
]

# All models (for detection)
ALL_MODELS: list[str] = [
    *MODEL_PRIORITY,
    *IMAGE_MODEL_PRIORITY,
    GEMINI_EMBEDDING,
]

ALL_MODELS_SET: set[str] = set(ALL_MODELS)

# ── Free-tier rate limits per model ─────────────────────────────────────────
# Source: ai.google.dev/gemini-api/docs/rate-limits (checked Feb 2026)
# Note: Rate limits are per-project (not per-key), reset at midnight PT
MODEL_RATE_LIMITS: dict[str, dict[str, int]] = {
    GEMINI_3_FLASH:        {"rpm": 5,  "rpd": 50,    "tpm": 250_000},
    GEMINI_25_PRO:         {"rpm": 5,  "rpd": 100,   "tpm": 250_000},
    GEMINI_25_FLASH:       {"rpm": 15, "rpd": 1_500, "tpm": 1_000_000},
    GEMINI_25_FLASH_IMAGE: {"rpm": 10, "rpd": 25,    "tpm": 250_000},
    GEMINI_25_FLASH_LITE:  {"rpm": 15, "rpd": 1_000, "tpm": 250_000},
    GEMINI_EMBEDDING:      {"rpm": 15, "rpd": 1_500, "tpm": 1_000_000},
}

# ── Model display names (short) ────────────────────────────────────────────
MODEL_SHORT_NAMES: dict[str, str] = {
    GEMINI_3_FLASH:        "3-flash",
    GEMINI_25_PRO:         "2.5-pro",
    GEMINI_25_FLASH:       "2.5-flash",
    GEMINI_25_FLASH_IMAGE: "2.5-flash-img",
    GEMINI_25_FLASH_LITE:  "2.5-flash-lite",
    GEMINI_EMBEDDING:      "embedding",
}

# ── Model capabilities ─────────────────────────────────────────────────────
CAP_TEXT = "text"
CAP_THINKING = "thinking"
CAP_FUNCTION_CALLING = "function_calling"
CAP_SEARCH_GROUNDING = "search_grounding"
CAP_CODE_EXECUTION = "code_execution"
CAP_URL_CONTEXT = "url_context"
CAP_STRUCTURED_OUTPUT = "structured_output"
CAP_MULTIMODAL_INPUT = "multimodal_input"
CAP_IMAGE_GENERATION = "image_generation"
CAP_EMBEDDING = "embedding"

MODEL_CAPABILITIES: dict[str, set[str]] = {
    GEMINI_3_FLASH: {
        CAP_TEXT, CAP_THINKING, CAP_FUNCTION_CALLING, CAP_SEARCH_GROUNDING,
        CAP_CODE_EXECUTION, CAP_URL_CONTEXT, CAP_STRUCTURED_OUTPUT, CAP_MULTIMODAL_INPUT,
    },
    GEMINI_25_PRO: {
        CAP_TEXT, CAP_THINKING, CAP_FUNCTION_CALLING, CAP_SEARCH_GROUNDING,
        CAP_CODE_EXECUTION, CAP_URL_CONTEXT, CAP_STRUCTURED_OUTPUT, CAP_MULTIMODAL_INPUT,
    },
    GEMINI_25_FLASH: {
        CAP_TEXT, CAP_THINKING, CAP_FUNCTION_CALLING, CAP_SEARCH_GROUNDING,
        CAP_CODE_EXECUTION, CAP_URL_CONTEXT, CAP_STRUCTURED_OUTPUT, CAP_MULTIMODAL_INPUT,
    },
    GEMINI_25_FLASH_IMAGE: {
        CAP_TEXT, CAP_IMAGE_GENERATION,
    },
    GEMINI_25_FLASH_LITE: {
        CAP_TEXT, CAP_THINKING, CAP_FUNCTION_CALLING, CAP_SEARCH_GROUNDING,
        CAP_CODE_EXECUTION, CAP_URL_CONTEXT, CAP_STRUCTURED_OUTPUT, CAP_MULTIMODAL_INPUT,
    },
    GEMINI_EMBEDDING: {
        CAP_EMBEDDING,
    },
}

# ── OpenAI model name mapping ──────────────────────────────────────────────
OPENAI_MODEL_MAP: dict[str, str] = {
    "gpt-4": GEMINI_25_PRO,
    "gpt-4-turbo": GEMINI_25_PRO,
    "gpt-4o": GEMINI_25_FLASH,
    "gpt-4o-mini": GEMINI_25_FLASH_LITE,
    "gpt-3.5-turbo": GEMINI_25_FLASH_LITE,
    "dall-e-3": GEMINI_25_FLASH_IMAGE,
    "dall-e-2": GEMINI_25_FLASH_IMAGE,
    "text-embedding-ada-002": GEMINI_EMBEDDING,
    "text-embedding-3-small": GEMINI_EMBEDDING,
    "text-embedding-3-large": GEMINI_EMBEDDING,
}

# ── Gemini API ──────────────────────────────────────────────────────────────
GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"
GEMINI_GENERATE_ENDPOINT = "{base}/models/{model}:generateContent"
GEMINI_MODELS_ENDPOINT = "{base}/models"
GEMINI_EMBED_ENDPOINT = "{base}/models/{model}:embedContent"
GEMINI_TEST_PROMPT = "Say OK"

# ── Redis key prefixes ────────────────────────────────────────────────────
REDIS_KEY_APIKEYS = "apikeys"
REDIS_KEY_ACTIVE_KEYS = "active_keys"
REDIS_KEY_RATELIMIT = "ratelimit"  # ratelimit:{key_hash}:{model}
REDIS_KEY_LOGS = "logs"
REDIS_KEY_STATS_HOURLY = "stats:hourly"  # stats:hourly:{YYYY-MM-DD-HH}
REDIS_KEY_CONFIG = "config"

# ── TTLs (seconds) ─────────────────────────────────────────────────────────
TTL_RATE_LIMIT = 86_400        # 24 hours
TTL_LOGS = 604_800             # 7 days
TTL_STATS_HOURLY = 86_400      # 24 hours

# ── Router defaults ────────────────────────────────────────────────────────
DEFAULT_HEALTH_WEIGHT = 0.4
DEFAULT_CAPACITY_WEIGHT = 0.6
DEFAULT_RETRY_ATTEMPTS = 3
DEFAULT_FALLBACK_ENABLED = True

# ── Health scoring ──────────────────────────────────────────────────────────
HEALTH_SCORE_MAX = 100
HEALTH_SCORE_SUCCESS_DELTA = 5
HEALTH_SCORE_FAILURE_DELTA = -10
HEALTH_CONSECUTIVE_ERROR_DISABLE = 5

# ── Background model re-detection interval (seconds) ───────────────────────
MODEL_REDETECT_INTERVAL = 300  # 5 minutes

# ── Server defaults ────────────────────────────────────────────────────────
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000

# ── Token estimation ───────────────────────────────────────────────────────
TOKEN_ESTIMATION_CHARS_PER_TOKEN = 4
TOKEN_ESTIMATION_BUFFER = 1.2
