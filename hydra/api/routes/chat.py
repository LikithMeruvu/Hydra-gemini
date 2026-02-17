"""POST /v1/chat/completions — OpenAI-compatible chat with FAST model fallback.

Supports both normal and streaming (SSE) responses.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from hydra.core.constants import (
    CAP_CODE_EXECUTION,
    CAP_FUNCTION_CALLING,
    CAP_IMAGE_GENERATION,
    CAP_SEARCH_GROUNDING,
    CAP_STRUCTURED_OUTPUT,
    CAP_URL_CONTEXT,
    OPENAI_MODEL_MAP,
)
from hydra.core.exceptions import AllKeysExhaustedError, GeminiAPIError
from hydra.models.schemas import (
    ChatChoice,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessage,
    RequestLogEntry,
    UsageInfo,
)
from hydra.services.gemini_client import GeminiClient
from hydra.core.redis_client import get_redis

logger = logging.getLogger(__name__)

router = APIRouter()


async def _get_raw_key(key_hash: str) -> str | None:
    r = await get_redis()
    return await r.hget("_plainkeys", key_hash)


def _detect_required_capabilities(request: ChatCompletionRequest) -> set[str]:
    caps: set[str] = set()
    if request.tools:
        for tool in request.tools:
            if "function_declarations" in tool or "functionDeclarations" in tool:
                caps.add(CAP_FUNCTION_CALLING)
            elif tool.get("type") == "function":
                caps.add(CAP_FUNCTION_CALLING)
            
            if "google_search" in tool or "googleSearch" in tool:
                caps.add(CAP_SEARCH_GROUNDING)
            if "code_execution" in tool or "codeExecution" in tool:
                caps.add(CAP_CODE_EXECUTION)
            if "url_context" in tool or "urlContext" in tool:
                caps.add(CAP_URL_CONTEXT)
    if request.response_modalities:
        if "IMAGE" in [m.upper() for m in request.response_modalities]:
            caps.add(CAP_IMAGE_GENERATION)
    if request.response_format:
        if request.response_format.get("type", "") in ("json_object", "json", "json_schema"):
            caps.add(CAP_STRUCTURED_OUTPUT)
    return caps


def _convert_tools(tools: list[dict] | None) -> list[dict] | None:
    """Convert OpenAI-format tools to Gemini format."""
    if not tools:
        return None
    
    gemini_tools = []
    function_declarations = []
    
    for tool in tools:
        # Pass through native Gemini tools
        if "function_declarations" in tool or "functionDeclarations" in tool:
            gemini_tools.append(tool)
            continue
        if "google_search" in tool or "code_execution" in tool:
            gemini_tools.append(tool)
            continue
            
        # Convert OpenAI function tool
        if tool.get("type") == "function":
            fn = tool.get("function", {})
            function_declarations.append({
                "name": fn.get("name"),
                "description": fn.get("description"),
                "parameters": fn.get("parameters"),
            })
            
    if function_declarations:
        gemini_tools.append({"function_declarations": function_declarations})
        
    return gemini_tools


def _convert_tool_choice(tool_choice: str | dict | None) -> dict | None:
    """Convert OpenAI tool_choice to Gemini toolConfig."""
    if not tool_choice:
        return None
        
    if tool_choice == "auto":
        return {"function_calling_config": {"mode": "AUTO"}}
    if tool_choice == "none":
        return {"function_calling_config": {"mode": "NONE"}}
    if tool_choice == "required":
        return {"function_calling_config": {"mode": "ANY"}}
        
    if isinstance(tool_choice, dict):
        if tool_choice.get("type") == "function":
            fn_name = tool_choice.get("function", {}).get("name")
            if fn_name:
                return {
                    "function_calling_config": {
                        "mode": "ANY",
                        "allowed_function_names": [fn_name],
                    }
                }
    return None


async def _generate_with_fallback(request: ChatCompletionRequest) -> dict:
    """Core fallback logic — returns the result dict or raises HTTPException."""
    from hydra.api.app import router_service, key_service, rate_limiter, stats_service, gemini_client

    if not router_service or not gemini_client:
        raise HTTPException(503, "Gateway not initialized")

    total_text = ""
    for m in request.messages:
        if isinstance(m.content, str):
            total_text += m.content + " "
        elif isinstance(m.content, list):
            for part in m.content:
                if isinstance(part, dict) and part.get("type") == "text":
                    total_text += part.get("text", "") + " "
    estimated_tokens = GeminiClient.estimate_tokens(total_text)

    preferred_model = OPENAI_MODEL_MAP.get(request.model, request.model)
    required_caps = _detect_required_capabilities(request)

    failed_pairs: set[tuple[str, str]] = set()
    failed_models: dict[str, int] = {}
    blocked_models: set[str] = set()
    last_error: Exception | None = None
    total_attempts = 0
    max_attempts = 20

    while total_attempts < max_attempts:
        total_attempts += 1

        try:
            key_hash, model, email, preview = await router_service.select_best_key_and_model(
                preferred_model=preferred_model,
                estimated_tokens=estimated_tokens,
                required_capabilities=required_caps if required_caps else None,
                exclude_pairs=failed_pairs,
                blocked_models=blocked_models,
            )
        except AllKeysExhaustedError:
            break

        api_key = await _get_raw_key(key_hash)
        if not api_key:
            logger.error("No plaintext key for %s", key_hash[:8])
            failed_pairs.add((key_hash, model))
            continue

        try:
            messages = [{"role": m.role, "content": m.content} for m in request.messages]

            result = await gemini_client.generate_content(
                api_key, model, messages,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                tools=_convert_tools(request.tools),
                tool_config=_convert_tool_choice(request.tool_choice) or request.tool_config,
                thinking=request.thinking,
                response_format=request.response_format,
                response_modalities=request.response_modalities,
            )

            await rate_limiter.record_request(key_hash, model, result["tokens"]["total_tokens"])
            await key_service.update_health(key_hash, success=True)

            response_content = result["content"]
            if result.get("images"):
                for i, img in enumerate(result["images"]):
                    mime = img.get("mime_type", "image/png")
                    data = img.get("data", "")
                    response_content += f"\n\n![Generated Image {i+1}](data:{mime};base64,{data})"

            finish_reason = "tool_calls" if result.get("function_calls") else "stop"

            await stats_service.log_request(RequestLogEntry(
                timestamp=datetime.now(timezone.utc),
                key_hash=key_hash, key_email=email, model=model,
                tokens_used=result["tokens"]["total_tokens"],
                estimated_tokens=estimated_tokens,
                success=True, latency_ms=result["latency_ms"],
                fallback_count=total_attempts - 1,
            ))

            metadata = {
                "key_email": email,
                "model_used": model,
                "latency_ms": result["latency_ms"],
                "fallback_count": total_attempts - 1,
            }
            if result.get("function_calls"):
                metadata["function_calls"] = result["function_calls"]
            if result.get("grounding_metadata"):
                metadata["grounding_metadata"] = result["grounding_metadata"]
            if result.get("images"):
                metadata["image_count"] = len(result["images"])

            return {
                "model": model,
                "content": response_content,
                "finish_reason": finish_reason,
                "tokens": result["tokens"],
                "metadata": metadata,
            }

        except GeminiAPIError as exc:
            logger.warning(
                "Attempt %d FAILED [%s / %s]: %s → trying next",
                total_attempts, model, email, str(exc)[:80],
            )
            last_error = exc
            failed_pairs.add((key_hash, model))

            if exc.status_code == 429:
                failed_models[model] = failed_models.get(model, 0) + 1
                if failed_models[model] >= 2:
                    logger.warning("Model %s got 429 on %d keys → BLOCKING", model, failed_models[model])
                    blocked_models.add(model)
            else:
                await key_service.update_health(key_hash, success=False)

            await stats_service.log_request(RequestLogEntry(
                timestamp=datetime.now(timezone.utc),
                key_hash=key_hash, key_email=email, model=model,
                estimated_tokens=estimated_tokens,
                success=False, error=str(exc)[:200],
                fallback_count=total_attempts - 1,
            ))
            continue

        except Exception as exc:
            logger.exception("Unexpected error on attempt %d", total_attempts)
            failed_pairs.add((key_hash, model))
            last_error = exc
            continue

    raise HTTPException(429, {
        "error": "All API keys exhausted across all models",
        "message": f"Tried {total_attempts} combos. Blocked: {list(blocked_models)}",
        "last_error": str(last_error)[:200] if last_error else "No keys available",
        "fallback_count": total_attempts,
    })


# ── Streaming SSE helpers ──────────────────────────────────────────────────

async def _stream_sse(result: dict, request_id: str):
    """Generate SSE chunks from a completed result.

    Since Gemini REST doesn't support streaming, we simulate it by
    chunking the completed response into small SSE events. This gives
    IDEs the streaming interface they expect.
    """
    model = result["model"]
    content = result["content"]
    finish_reason = result["finish_reason"]
    created = int(datetime.now(timezone.utc).timestamp())

    # Send content in chunks (~30 chars each for natural feel)
    chunk_size = 30
    for i in range(0, len(content), chunk_size):
        chunk = content[i:i + chunk_size]
        data = {
            "id": request_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{
                "index": 0,
                "delta": {"content": chunk},
                "finish_reason": None,
            }],
        }
        yield f"data: {json.dumps(data)}\n\n"
        await asyncio.sleep(0.01)  # Small delay for natural feel

    # Final chunk with finish_reason
    final = {
        "id": request_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [{
            "index": 0,
            "delta": {},
            "finish_reason": finish_reason,
        }],
    }
    yield f"data: {json.dumps(final)}\n\n"
    yield "data: [DONE]\n\n"


# ── Main endpoint ──────────────────────────────────────────────────────────

@router.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest, raw_request: Request):
    """OpenAI-compatible chat — supports both regular and streaming responses."""
    from hydra.api.app import token_service

    result = await _generate_with_fallback(request)

    # Track token usage if authenticated
    bearer_token = getattr(raw_request.state, "bearer_token", None)
    if bearer_token and token_service:
        await token_service.record_usage(bearer_token, result["model"], result["tokens"]["total_tokens"])

    request_id = f"chatcmpl-{uuid4().hex[:8]}"

    # ── Streaming response ──
    if request.stream:
        return StreamingResponse(
            _stream_sse(result, request_id),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # ── Normal response ──
    # Construct tool_calls if present
    tool_calls = None
    if result.get("metadata", {}).get("function_calls"):
        tool_calls = []
        for fc in result["metadata"]["function_calls"]:
            tool_calls.append({
                "id": f"call_{uuid4().hex[:8]}",
                "type": "function",
                "function": {
                    "name": fc["name"],
                    "arguments": json.dumps(fc["arguments"]),
                }
            })

    return ChatCompletionResponse(
        id=request_id,
        model=result["model"],
        choices=[ChatChoice(
            message=ChatMessage(
                role="assistant", 
                content=result["content"],
                tool_calls=tool_calls
            ),
            finish_reason=result["finish_reason"],
        )],
        usage=UsageInfo(**result["tokens"]),
        hydra_metadata=result["metadata"],
    )
