"""Gemini adapter."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx

from core.schemas.constants import AGENT_TIMEOUT_SECONDS, HEALTH_CHECK_MAX_TOKENS

from .base import CompletionResult, Message, ProviderError, ToolCall, ToolDefinition


class GeminiAdapter:
    """Adapter for Gemini generateContent API."""

    provider_name = "gemini"

    def __init__(
        self,
        base_url: str,
        api_key: str,
        default_model: str | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.default_model = default_model
        self.transport = transport

    async def complete(
        self,
        messages: list[Message],
        model: str,
        tools: list[ToolDefinition] | None = None,
        response_format: dict[str, Any] | None = None,
    ) -> CompletionResult:
        """Execute a generateContent call."""

        contents = [
            {
                "role": message.role,
                "parts": [{"text": message.content}],
            }
            for message in messages
        ]
        payload: dict[str, Any] = {"contents": contents}
        if tools:
            payload["tools"] = [
                {
                    "function_declarations": [
                        {
                            "name": tool.name,
                            "description": tool.description,
                            "parameters": tool.parameters,
                        }
                        for tool in tools
                    ]
                }
            ]
        if response_format:
            payload["response_format"] = response_format

        url = f"{self.base_url}/models/{model}:generateContent"
        headers = {"x-goog-api-key": self.api_key}
        start = time.monotonic()
        async with httpx.AsyncClient(
            timeout=AGENT_TIMEOUT_SECONDS, transport=self.transport
        ) as client:
            response = await self._post_with_retry(client, url, headers, payload, model=model)
        latency_ms = int((time.monotonic() - start) * 1000)

        data = response.json()
        candidate = data["candidates"][0]
        parts = candidate.get("content", {}).get("parts", [])
        text_parts = [part.get("text", "") for part in parts if "text" in part]
        text = "".join(text_parts)
        tool_calls: list[ToolCall] = []
        for part in parts:
            if "functionCall" in part:
                call = part["functionCall"]
                tool_calls.append(
                    ToolCall(name=call.get("name", ""), arguments=call.get("args", {}))
                )

        usage = data.get("usageMetadata", {})
        finish_reason = candidate.get("finishReason")

        return CompletionResult(
            text=text,
            tool_calls=tool_calls,
            usage=usage,
            finish_reason=finish_reason,
            latency_ms=latency_ms,
        )

    async def health_check(self) -> bool:
        """Return True if a minimal request succeeds."""

        if not self.default_model:
            return False
        payload = {
            "contents": [{"role": "user", "parts": [{"text": "ping"}]}],
            "generationConfig": {"maxOutputTokens": HEALTH_CHECK_MAX_TOKENS},
        }
        url = f"{self.base_url}/models/{self.default_model}:generateContent"
        headers = {"x-goog-api-key": self.api_key}
        try:
            async with httpx.AsyncClient(
                timeout=AGENT_TIMEOUT_SECONDS, transport=self.transport
            ) as client:
                await self._post_with_retry(client, url, headers, payload, model=self.default_model)
        except ProviderError:
            return False
        return True

    async def list_models(self) -> list[str] | None:
        """Gemini does not provide a compatible /models endpoint."""

        return None

    async def _post_with_retry(
        self,
        client: httpx.AsyncClient,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
        model: str | None = None,
    ) -> httpx.Response:
        try:
            response = await client.post(url, headers=headers, json=payload)
        except httpx.TimeoutException as exc:
            raise ProviderError(self.provider_name, None, str(exc), model=model) from exc

        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            delay = float(retry_after) if retry_after else 1.0
            await asyncio.sleep(delay)
            try:
                response = await client.post(url, headers=headers, json=payload)
            except httpx.TimeoutException as exc:
                raise ProviderError(self.provider_name, None, str(exc), model=model) from exc

        if response.status_code >= 400:
            raise ProviderError(
                self.provider_name,
                response.status_code,
                response.text,
                model=model,
            )

        return response
