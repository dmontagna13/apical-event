"""Anthropic adapter."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx

from core.schemas.constants import AGENT_TIMEOUT_SECONDS, HEALTH_CHECK_MAX_TOKENS

from .base import CompletionResult, Message, ProviderError, ToolCall, ToolDefinition


class AnthropicAdapter:
    """Adapter for Anthropic messages API."""

    provider_name = "anthropic"

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
        """Execute a messages call."""

        payload: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": message.role, "content": message.content} for message in messages
            ],
            "max_tokens": 1024,
        }
        if tools:
            payload["tools"] = [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.parameters,
                }
                for tool in tools
            ]
        if response_format:
            payload["response_format"] = response_format

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
        }
        url = f"{self.base_url}/messages"
        start = time.monotonic()
        async with httpx.AsyncClient(
            timeout=AGENT_TIMEOUT_SECONDS, transport=self.transport
        ) as client:
            response = await self._post_with_retry(client, url, headers, payload, model=model)
        latency_ms = int((time.monotonic() - start) * 1000)

        data = response.json()
        content_blocks = data.get("content", [])
        text_parts = [
            block.get("text", "") for block in content_blocks if block.get("type") == "text"
        ]
        text = "".join(text_parts)
        tool_calls: list[ToolCall] = []
        for block in content_blocks:
            if block.get("type") == "tool_use":
                tool_calls.append(
                    ToolCall(name=block.get("name", ""), arguments=block.get("input", {}))
                )

        return CompletionResult(
            text=text,
            tool_calls=tool_calls,
            usage=data.get("usage", {}),
            finish_reason=data.get("stop_reason"),
            latency_ms=latency_ms,
        )

    async def health_check(self) -> bool:
        """Return True if a minimal request succeeds."""

        if not self.default_model:
            return False
        payload = {
            "model": self.default_model,
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": HEALTH_CHECK_MAX_TOKENS,
        }
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
        }
        url = f"{self.base_url}/messages"
        try:
            async with httpx.AsyncClient(
                timeout=AGENT_TIMEOUT_SECONDS, transport=self.transport
            ) as client:
                await self._post_with_retry(client, url, headers, payload, model=self.default_model)
        except ProviderError:
            return False
        return True

    async def list_models(self) -> list[str] | None:
        """Anthropic does not provide a compatible /models endpoint."""

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
            raise ProviderError(self.provider_name, response.status_code, response.text, model=model)

        return response
