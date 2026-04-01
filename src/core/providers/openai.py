"""OpenAI-compatible adapter."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import httpx

from core.schemas.constants import AGENT_TIMEOUT_SECONDS, HEALTH_CHECK_MAX_TOKENS

from .base import CompletionResult, Message, ProviderError, ToolCall, ToolDefinition


class OpenAIAdapter:
    """Adapter for OpenAI-compatible chat completions."""

    provider_name = "openai"

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
        """Execute a chat completion call."""

        payload: dict[str, Any] = {
            "model": model,
            "messages": [
                {
                    "role": message.role,
                    "content": message.content,
                }
                for message in messages
            ],
        }
        if tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters,
                    },
                }
                for tool in tools
            ]
        if response_format:
            payload["response_format"] = response_format

        headers = {"Authorization": f"Bearer {self.api_key}"}
        url = f"{self.base_url}/chat/completions"
        start = time.monotonic()
        async with httpx.AsyncClient(
            timeout=AGENT_TIMEOUT_SECONDS, transport=self.transport
        ) as client:
            response = await self._post_with_retry(client, url, headers, payload)
        latency_ms = int((time.monotonic() - start) * 1000)

        data = response.json()
        choice = data["choices"][0]
        message = choice.get("message", {})
        text = message.get("content") or ""
        tool_calls = []
        for tool_call in message.get("tool_calls", []) or []:
            fn = tool_call.get("function", {})
            raw_args = fn.get("arguments", "{}")
            if isinstance(raw_args, str):
                try:
                    args = json.loads(raw_args)
                except json.JSONDecodeError:
                    args = {}
            elif isinstance(raw_args, dict):
                args = raw_args
            else:
                args = {}
            tool_calls.append(ToolCall(name=fn.get("name", ""), arguments=args))

        return CompletionResult(
            text=text,
            tool_calls=tool_calls,
            usage=data.get("usage", {}),
            finish_reason=choice.get("finish_reason"),
            latency_ms=latency_ms,
        )

    async def health_check(self) -> bool:
        """Return True if a minimal completion succeeds."""

        if not self.default_model:
            return False
        try:
            headers = {"Authorization": f"Bearer {self.api_key}"}
            url = f"{self.base_url}/chat/completions"
            payload = {
                "model": self.default_model,
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": HEALTH_CHECK_MAX_TOKENS,
            }
            async with httpx.AsyncClient(
                timeout=AGENT_TIMEOUT_SECONDS, transport=self.transport
            ) as client:
                await self._post_with_retry(client, url, headers, payload)
        except ProviderError:
            return False
        return True

    async def _post_with_retry(
        self,
        client: httpx.AsyncClient,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
    ) -> httpx.Response:
        try:
            response = await client.post(url, headers=headers, json=payload)
        except httpx.TimeoutException as exc:
            raise ProviderError(self.provider_name, None, str(exc)) from exc

        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            delay = float(retry_after) if retry_after else 1.0
            await asyncio.sleep(delay)
            try:
                response = await client.post(url, headers=headers, json=payload)
            except httpx.TimeoutException as exc:
                raise ProviderError(self.provider_name, None, str(exc)) from exc

        if response.status_code >= 400:
            raise ProviderError(self.provider_name, response.status_code, response.text)

        return response
