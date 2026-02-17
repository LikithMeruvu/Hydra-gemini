"""Gemini API client — wraps HTTP calls to the Gemini REST API.

Supports: text generation, multimodal input, function calling, search grounding,
code execution, image generation, structured output, thinking, URL context, embeddings.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import time
from typing import Any, Optional

import httpx

from hydra.core.constants import (
    ALL_MODELS_SET,
    GEMINI_API_BASE,
    TOKEN_ESTIMATION_BUFFER,
    TOKEN_ESTIMATION_CHARS_PER_TOKEN,
)
from hydra.core.exceptions import GeminiAPIError

logger = logging.getLogger(__name__)


class GeminiClient:
    """Async wrapper around the Gemini REST API with full feature support."""

    def __init__(self, timeout: float = 60.0):
        self._timeout = timeout

    # ── model detection ────────────────────────────────────────────────────

    async def list_models_from_api(self, api_key: str) -> list[str]:
        """Call GET /v1beta/models — returns all model IDs the key can access.

        This is a lightweight metadata call that does NOT consume generateContent
        rate limits, making it far more reliable than probing with actual requests.
        """
        url = f"{GEMINI_API_BASE}/models"
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(url, params={"key": api_key, "pageSize": 1000})
            if resp.status_code == 200:
                data = resp.json()
                models = []
                for m in data.get("models", []):
                    model_id = m.get("name", "").replace("models/", "")
                    if model_id:
                        models.append(model_id)
                return models
            else:
                logger.warning("models.list returned %d: %s", resp.status_code, resp.text[:200])
                return []
        except Exception as exc:
            logger.warning("models.list failed: %s", exc)
            return []

    async def detect_available_models(self, api_key: str, models: list[str]) -> list[str]:
        """Detect which models from the given list this key can access.

        Strategy:
        1. Use models.list API (reliable, no rate-limit cost) with 3 retries
        2. Filter the result against our known model list
        3. If models.list fails entirely, fall back to parallel generateContent probing
        """
        # Try models.list with retries
        for attempt in range(3):
            all_api_models = await self.list_models_from_api(api_key)
            if all_api_models:
                # Filter to only our known models
                available = [m for m in models if m in all_api_models]
                if available:
                    return available
                # models.list returned results but none match our list — that's valid
                # (key might not have access to any of the requested models)
                return []
            # Backoff before retry
            if attempt < 2:
                await asyncio.sleep(1 * (attempt + 1))

        # Fallback: parallel generateContent probing
        logger.warning("models.list failed after 3 retries, falling back to probing")
        return await self._probe_models_parallel(api_key, models)

    async def _probe_models_parallel(self, api_key: str, models: list[str]) -> list[str]:
        """Probe models in parallel using generateContent (fallback method)."""
        async def _probe(model: str) -> str | None:
            for attempt in range(2):
                if await self.test_api_key(api_key, model):
                    return model
                if attempt < 1:
                    await asyncio.sleep(0.5)
            return None

        results = await asyncio.gather(*[_probe(m) for m in models], return_exceptions=True)
        return [r for r in results if isinstance(r, str)]

    # ── content generation ─────────────────────────────────────────────────

    async def generate_content(
        self,
        api_key: str,
        model: str,
        messages: list[dict],
        *,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        tools: Optional[list[dict]] = None,
        tool_config: Optional[dict] = None,
        thinking: Optional[dict] = None,
        response_format: Optional[dict] = None,
        response_modalities: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """Call Gemini generateContent with full feature support.

        Parameters
        ----------
        messages : list of dicts with 'role' and 'content' keys.
            content can be a string or a list of parts (for multimodal).
        tools : Gemini tools array (function_declarations, google_search, code_execution, url_context)
        tool_config : Gemini tool_config for function calling mode
        thinking : {"thinking_budget": int} to control reasoning depth
        response_format : {"type": "json", "schema": {...}} for structured output
        response_modalities : ["TEXT", "IMAGE"] to request image generation

        Returns
        -------
        dict with keys: content, tokens, latency_ms, model, parts, function_calls
        """
        url = f"{GEMINI_API_BASE}/models/{model}:generateContent"
        body = self._build_request_body(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
            tool_config=tool_config,
            thinking=thinking,
            response_format=response_format,
            response_modalities=response_modalities,
        )

        t0 = time.perf_counter()
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(url, params={"key": api_key}, json=body)

        latency_ms = int((time.perf_counter() - t0) * 1000)

        if resp.status_code != 200:
            detail = resp.text[:300]
            raise GeminiAPIError(resp.status_code, detail, model=model)

        data = resp.json()
        return self._parse_response(data, latency_ms, model)

    # ── embeddings ─────────────────────────────────────────────────────────

    async def embed_content(
        self,
        api_key: str,
        model: str,
        texts: list[str],
    ) -> dict[str, Any]:
        """Generate embeddings for a batch of texts.

        Uses batchEmbedContents for efficiency when multiple texts are provided.
        """
        if len(texts) == 1:
            return await self._embed_single(api_key, model, texts[0])
        return await self._embed_batch(api_key, model, texts)

    async def _embed_single(self, api_key: str, model: str, text: str) -> dict[str, Any]:
        """Embed a single text."""
        url = f"{GEMINI_API_BASE}/models/{model}:embedContent"
        body = {"content": {"parts": [{"text": text}]}}

        t0 = time.perf_counter()
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, params={"key": api_key}, json=body)
        latency_ms = int((time.perf_counter() - t0) * 1000)

        if resp.status_code != 200:
            raise GeminiAPIError(resp.status_code, resp.text[:300], model=model)

        data = resp.json()
        embedding = data.get("embedding", {}).get("values", [])
        return {
            "embeddings": [embedding],
            "model": model,
            "latency_ms": latency_ms,
        }

    async def _embed_batch(self, api_key: str, model: str, texts: list[str]) -> dict[str, Any]:
        """Embed multiple texts using batchEmbedContents."""
        url = f"{GEMINI_API_BASE}/models/{model}:batchEmbedContents"
        requests_body = [
            {"model": f"models/{model}", "content": {"parts": [{"text": t}]}}
            for t in texts
        ]
        body = {"requests": requests_body}

        t0 = time.perf_counter()
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(url, params={"key": api_key}, json=body)
        latency_ms = int((time.perf_counter() - t0) * 1000)

        if resp.status_code != 200:
            raise GeminiAPIError(resp.status_code, resp.text[:300], model=model)

        data = resp.json()
        embeddings = [
            e.get("values", [])
            for e in data.get("embeddings", [])
        ]
        return {
            "embeddings": embeddings,
            "model": model,
            "latency_ms": latency_ms,
        }

    # ── health check ───────────────────────────────────────────────────────

    async def test_api_key(self, api_key: str, model: str) -> bool:
        """Lightweight health-check request. Returns True if the key works."""
        url = f"{GEMINI_API_BASE}/models/{model}:generateContent"
        body = {
            "contents": [{"parts": [{"text": "Say OK"}]}],
            "generationConfig": {"maxOutputTokens": 5},
        }
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(url, params={"key": api_key}, json=body)
            return resp.status_code == 200
        except Exception:
            return False

    # ── helpers ─────────────────────────────────────────────────────────────

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """Conservative token count estimation."""
        if not text:
            return 0
        return int((len(text) / TOKEN_ESTIMATION_CHARS_PER_TOKEN) * TOKEN_ESTIMATION_BUFFER)

    @staticmethod
    def _build_request_body(
        messages: list[dict],
        *,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        tools: Optional[list[dict]] = None,
        tool_config: Optional[dict] = None,
        thinking: Optional[dict] = None,
        response_format: Optional[dict] = None,
        response_modalities: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """Convert messages to Gemini format with full feature support."""
        contents: list[dict[str, Any]] = []
        system_text: str | None = None

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if role == "system":
                # System messages become systemInstruction
                if isinstance(content, str):
                    system_text = content
                else:
                    # Multimodal system message — extract text parts
                    texts = [p.get("text", "") for p in content if p.get("type") == "text"]
                    system_text = " ".join(texts)
                continue

            gemini_role = "model" if role == "assistant" else "user"

            if isinstance(content, str):
                # Simple text message
                contents.append({"role": gemini_role, "parts": [{"text": content}]})
            elif isinstance(content, list):
                # Multimodal message (OpenAI format → Gemini format)
                parts = GeminiClient._convert_parts(content)
                contents.append({"role": gemini_role, "parts": parts})
            else:
                contents.append({"role": gemini_role, "parts": [{"text": str(content)}]})

        body: dict[str, Any] = {"contents": contents}

        if system_text:
            body["systemInstruction"] = {"parts": [{"text": system_text}]}

        # Tools (function calling, search grounding, code execution, URL context)
        if tools:
            body["tools"] = tools
        if tool_config:
            body["toolConfig"] = tool_config

        # Generation config
        gen_config: dict[str, Any] = {}
        if temperature is not None:
            gen_config["temperature"] = temperature
        if max_tokens is not None and max_tokens > 0:
            gen_config["maxOutputTokens"] = max_tokens

        # Thinking / reasoning
        if thinking:
            budget = thinking.get("thinking_budget", thinking.get("thinkingBudget"))
            if budget is not None:
                gen_config["thinkingConfig"] = {"thinkingBudget": budget}

        # Response modalities (for image generation)
        if response_modalities:
            gen_config["responseModalities"] = [m.upper() for m in response_modalities]

        # Structured output
        if response_format:
            fmt_type = response_format.get("type", "")
            if fmt_type in ("json_object", "json"):
                gen_config["responseMimeType"] = "application/json"
            elif fmt_type == "json_schema":
                gen_config["responseMimeType"] = "application/json"
                schema = response_format.get("json_schema", {}).get("schema")
                if schema:
                    gen_config["responseSchema"] = schema

        if gen_config:
            body["generationConfig"] = gen_config

        return body

    @staticmethod
    def _convert_parts(content_parts: list[dict]) -> list[dict[str, Any]]:
        """Convert OpenAI-style multimodal parts to Gemini parts.

        Handles:
        - {"type": "text", "text": "..."} → {"text": "..."}
        - {"type": "image_url", "image_url": {"url": "data:..."}} → {"inline_data": {...}}
        - {"type": "image_url", "image_url": {"url": "https://..."}} → {"file_data": {...}}
        - Gemini-native parts (already have "text" or "inline_data") pass through
        """
        gemini_parts: list[dict[str, Any]] = []

        for part in content_parts:
            if isinstance(part, str):
                gemini_parts.append({"text": part})
                continue

            part_type = part.get("type", "")

            if part_type == "text":
                gemini_parts.append({"text": part.get("text", "")})

            elif part_type == "image_url":
                image_url_data = part.get("image_url", {})
                url = image_url_data.get("url", "") if isinstance(image_url_data, dict) else str(image_url_data)

                if url.startswith("data:"):
                    # Base64 data URI → inline_data
                    # Format: data:image/png;base64,iVBOR...
                    header, b64_data = url.split(",", 1)
                    mime_type = header.split(":")[1].split(";")[0]
                    gemini_parts.append({
                        "inlineData": {
                            "mimeType": mime_type,
                            "data": b64_data,
                        }
                    })
                else:
                    # URL — use fileData (Gemini can fetch URLs)
                    gemini_parts.append({
                        "fileData": {
                            "mimeType": "image/jpeg",
                            "fileUri": url,
                        }
                    })

            elif part_type == "audio_url":
                audio_data = part.get("audio_url", {})
                url = audio_data.get("url", "") if isinstance(audio_data, dict) else str(audio_data)
                if url.startswith("data:"):
                    header, b64_data = url.split(",", 1)
                    mime_type = header.split(":")[1].split(";")[0]
                    gemini_parts.append({
                        "inlineData": {"mimeType": mime_type, "data": b64_data}
                    })

            elif part_type == "video_url":
                video_data = part.get("video_url", {})
                url = video_data.get("url", "") if isinstance(video_data, dict) else str(video_data)
                if url.startswith("data:"):
                    header, b64_data = url.split(",", 1)
                    mime_type = header.split(":")[1].split(";")[0]
                    gemini_parts.append({
                        "inlineData": {"mimeType": mime_type, "data": b64_data}
                    })

            else:
                # Pass through Gemini-native parts (text, inlineData, etc.)
                if "text" in part:
                    gemini_parts.append({"text": part["text"]})
                elif "inlineData" in part or "inline_data" in part:
                    gemini_parts.append(part)
                elif "fileData" in part or "file_data" in part:
                    gemini_parts.append(part)
                else:
                    # Unknown part type — try as text
                    gemini_parts.append({"text": str(part)})

        return gemini_parts

    @staticmethod
    def _parse_response(data: dict, latency_ms: int, model: str) -> dict[str, Any]:
        """Extract content, images, function calls, and token counts from Gemini response."""
        text_content = ""
        image_parts: list[dict] = []
        function_calls: list[dict] = []
        all_parts: list[dict] = []
        grounding_metadata: dict | None = None

        candidates = data.get("candidates", [])
        if candidates:
            candidate = candidates[0]
            parts = candidate.get("content", {}).get("parts", [])

            for part in parts:
                all_parts.append(part)

                if "text" in part:
                    text_content += part["text"]

                elif "inlineData" in part:
                    # Image output from image generation models
                    image_parts.append({
                        "mime_type": part["inlineData"].get("mimeType", "image/png"),
                        "data": part["inlineData"].get("data", ""),
                    })

                elif "functionCall" in part:
                    fc = part["functionCall"]
                    function_calls.append({
                        "name": fc.get("name", ""),
                        "arguments": fc.get("args", {}),
                    })

                elif "executableCode" in part:
                    # Code execution output
                    text_content += f"\n```{part['executableCode'].get('language', 'python')}\n"
                    text_content += part["executableCode"].get("code", "")
                    text_content += "\n```\n"

                elif "codeExecutionResult" in part:
                    text_content += f"\n**Execution Output:**\n```\n"
                    text_content += part["codeExecutionResult"].get("output", "")
                    text_content += "\n```\n"

            # Grounding metadata (search results, etc.)
            gm = candidate.get("groundingMetadata")
            if gm:
                grounding_metadata = gm
                # Append search suggestions to text if present
                search_queries = gm.get("searchEntryPoint", {}).get("renderedContent", "")
                grounding_chunks = gm.get("groundingChunks", [])
                if grounding_chunks and not text_content.endswith("\n\n---\n"):
                    sources = []
                    for chunk in grounding_chunks:
                        web = chunk.get("web", {})
                        if web:
                            title = web.get("title", "Source")
                            uri = web.get("uri", "")
                            sources.append(f"- [{title}]({uri})")
                    if sources:
                        text_content += "\n\n---\n**Sources:**\n" + "\n".join(sources) + "\n"

        usage = data.get("usageMetadata", {})

        result = {
            "content": text_content,
            "tokens": {
                "prompt_tokens": usage.get("promptTokenCount", 0),
                "completion_tokens": usage.get("candidatesTokenCount", 0),
                "total_tokens": usage.get("totalTokenCount", 0),
            },
            "latency_ms": latency_ms,
            "model": model,
            "parts": all_parts,
            "images": image_parts,
            "function_calls": function_calls,
        }

        if grounding_metadata:
            result["grounding_metadata"] = grounding_metadata

        return result
