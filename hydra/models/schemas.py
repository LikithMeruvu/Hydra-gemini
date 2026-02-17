"""Pydantic schemas shared across Hydra."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional, Union
from uuid import uuid4

from pydantic import BaseModel, Field


# ── API Key Storage ─────────────────────────────────────────────────────────


class APIKeyEntry(BaseModel):
    """Stored representation of a Gemini API key in Redis."""

    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    email: str
    api_key_preview: str = ""  # last 6 chars
    project_id: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_validated: Optional[datetime] = None
    is_active: bool = True
    health_score: int = 100
    consecutive_errors: int = 0
    available_models: list[str] = Field(default_factory=list)
    notes: str = ""


# ── OpenAI-compatible request/response ──────────────────────────────────────


class ChatMessage(BaseModel):
    role: str
    content: Union[str, list[dict]] = ""  # string or multimodal parts array
    tool_calls: Optional[list[dict]] = None  # OpenAI format tool calls


class ChatCompletionRequest(BaseModel):
    model: str = "gemini-2.5-flash"
    messages: list[ChatMessage]
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    stream: bool = False
    # Gemini-native features
    tools: Optional[list[dict]] = None               # function calling, search, code exec
    tool_choice: Optional[Union[str, dict]] = None    # OpenAI: "auto", "none", or {"type": "function", ...}
    tool_config: Optional[dict] = None                # Gemini native config
    thinking: Optional[dict] = None                   # {"thinking_budget": 1024}
    response_format: Optional[dict] = None            # {"type": "json_schema", "json_schema": {...}}
    response_modalities: Optional[list[str]] = None   # ["TEXT", "IMAGE"]


class ChatChoice(BaseModel):
    index: int = 0
    message: ChatMessage
    finish_reason: str = "stop"


class UsageInfo(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatCompletionResponse(BaseModel):
    id: str = Field(default_factory=lambda: f"chatcmpl-{uuid4().hex[:8]}")
    object: str = "chat.completion"
    created: int = Field(default_factory=lambda: int(datetime.utcnow().timestamp()))
    model: str = ""
    choices: list[ChatChoice] = Field(default_factory=list)
    usage: UsageInfo = Field(default_factory=UsageInfo)
    # Hydra metadata
    hydra_metadata: Optional[dict[str, Any]] = None


# ── Embeddings ──────────────────────────────────────────────────────────────


class EmbeddingRequest(BaseModel):
    model: str = "gemini-embedding-001"
    input: Union[str, list[str]]  # single string or list of strings
    encoding_format: str = "float"  # OpenAI compat


class EmbeddingData(BaseModel):
    object: str = "embedding"
    index: int = 0
    embedding: list[float] = Field(default_factory=list)


class EmbeddingResponse(BaseModel):
    object: str = "list"
    data: list[EmbeddingData] = Field(default_factory=list)
    model: str = ""
    usage: UsageInfo = Field(default_factory=UsageInfo)


# ── Rate Limit Status ──────────────────────────────────────────────────────


class RateLimitStatus(BaseModel):
    rpm_used: int = 0
    rpm_limit: int = 0
    rpd_used: int = 0
    rpd_limit: int = 0
    tpm_used: int = 0
    tpm_limit: int = 0


# ── Request Log Entry ──────────────────────────────────────────────────────


class RequestLogEntry(BaseModel):
    id: str = Field(default_factory=lambda: f"req_{uuid4().hex[:8]}")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    key_hash: str = ""
    key_email: str = ""
    model: str = ""
    tokens_used: int = 0
    estimated_tokens: int = 0
    success: bool = True
    latency_ms: int = 0
    error: Optional[str] = None
    fallback_count: int = 0


# ── Health Endpoint ────────────────────────────────────────────────────────


class HealthResponse(BaseModel):
    status: str = "ok"
    redis_connected: bool = False
    active_keys: int = 0
    uptime_seconds: float = 0
    version: str = ""
