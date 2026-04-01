"""Provider adapter tests with mocked HTTP transport."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

import httpx
import pytest

from core.config import ProviderConfig
from core.providers import (
    CompletionResult,
    Message,
    ProviderError,
    ToolCall,
    ToolDefinition,
    get_adapter,
)
from core.providers.anthropic import AnthropicAdapter
from core.providers.deepseek import DeepSeekAdapter
from core.providers.gemini import GeminiAdapter
from core.providers.openai import OpenAIAdapter

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "mock_provider_responses"


def _load_fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES_DIR / name).read_text())


def _make_transport(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("adapter_cls", "fixture"),
    [
        (OpenAIAdapter, "openai_text.json"),
        (GeminiAdapter, "gemini_text.json"),
        (AnthropicAdapter, "anthropic_text.json"),
        (DeepSeekAdapter, "deepseek_text.json"),
    ],
)
async def test_text_response(adapter_cls, fixture) -> None:
    data = _load_fixture(fixture)

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=data)

    adapter = adapter_cls(
        base_url="https://example.com",
        api_key="test",
        default_model="model",
        transport=_make_transport(handler),
    )
    result = await adapter.complete(messages=[Message(role="user", content="hi")], model="model")
    assert isinstance(result, CompletionResult)
    assert isinstance(result.text, str)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("adapter_cls", "fixture"),
    [
        (OpenAIAdapter, "openai_tool_call.json"),
        (GeminiAdapter, "gemini_tool_call.json"),
        (AnthropicAdapter, "anthropic_tool_call.json"),
        (DeepSeekAdapter, "openai_tool_call.json"),
    ],
)
async def test_tool_call_parsing(adapter_cls, fixture) -> None:
    data = _load_fixture(fixture)

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=data)

    adapter = adapter_cls(
        base_url="https://example.com",
        api_key="test",
        default_model="model",
        transport=_make_transport(handler),
    )
    result = await adapter.complete(messages=[Message(role="user", content="hi")], model="model")
    assert result.tool_calls == [ToolCall(name="update_kanban", arguments={"question_id": "Q-01"})]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "adapter_cls",
    [OpenAIAdapter, GeminiAdapter, AnthropicAdapter, DeepSeekAdapter],
)
async def test_error_responses(adapter_cls) -> None:
    for status in (401, 500):

        def handler(_: httpx.Request, status_code=status) -> httpx.Response:
            return httpx.Response(status_code, text="error")

        adapter = adapter_cls(
            base_url="https://example.com",
            api_key="test",
            default_model="model",
            transport=_make_transport(handler),
        )
        with pytest.raises(ProviderError) as excinfo:
            await adapter.complete(messages=[Message(role="user", content="hi")], model="model")
        assert excinfo.value.status_code == status


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("adapter_cls", "fixture"),
    [
        (OpenAIAdapter, "openai_text.json"),
        (GeminiAdapter, "gemini_text.json"),
        (AnthropicAdapter, "anthropic_text.json"),
        (DeepSeekAdapter, "openai_text.json"),
    ],
)
async def test_retry_on_429(adapter_cls, fixture) -> None:
    data = _load_fixture(fixture)
    calls = {"count": 0}

    def handler(_: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            return httpx.Response(429, headers={"Retry-After": "0"}, text="rate limit")
        return httpx.Response(200, json=data)

    adapter = adapter_cls(
        base_url="https://example.com",
        api_key="test",
        default_model="model",
        transport=_make_transport(handler),
    )
    result = await adapter.complete(messages=[Message(role="user", content="hi")], model="model")
    assert result.text
    assert calls["count"] == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "adapter_cls",
    [OpenAIAdapter, GeminiAdapter, AnthropicAdapter, DeepSeekAdapter],
)
async def test_timeout(adapter_cls) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout")

    adapter = adapter_cls(
        base_url="https://example.com",
        api_key="test",
        default_model="model",
        transport=_make_transport(handler),
    )
    with pytest.raises(ProviderError):
        await adapter.complete(messages=[Message(role="user", content="hi")], model="model")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "adapter_cls",
    [OpenAIAdapter, GeminiAdapter, AnthropicAdapter, DeepSeekAdapter],
)
async def test_health_check(adapter_cls) -> None:
    def ok_handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_load_fixture("openai_text.json"))

    adapter = adapter_cls(
        base_url="https://example.com",
        api_key="test",
        default_model="model",
        transport=_make_transport(ok_handler),
    )
    assert await adapter.health_check() is True

    def fail_handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="error")

    adapter = adapter_cls(
        base_url="https://example.com",
        api_key="test",
        default_model="model",
        transport=_make_transport(fail_handler),
    )
    assert await adapter.health_check() is False


def test_factory_unknown_provider() -> None:
    config = ProviderConfig(
        display_name="Test",
        base_url="https://example.com",
        api_key_env=None,
        api_key="test",
        default_model="model",
        available_models=["model"],
        supports_function_calling=True,
        supports_structured_output=True,
        max_context_tokens=1,
    )
    with pytest.raises(ValueError):
        get_adapter("unknown", config)


def test_factory_known_provider() -> None:
    config = ProviderConfig(
        display_name="Test",
        base_url="https://example.com",
        api_key_env=None,
        api_key="test",
        default_model="model",
        available_models=["model"],
        supports_function_calling=True,
        supports_structured_output=True,
        max_context_tokens=1,
    )
    adapter = get_adapter("openai", config)
    assert isinstance(adapter, OpenAIAdapter)


def test_tool_definition_usage() -> None:
    tool = ToolDefinition(
        name="update_kanban",
        description="Update",
        parameters={"type": "object", "properties": {}},
    )
    assert tool.name == "update_kanban"
