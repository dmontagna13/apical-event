"""Provider adapter protocol and shared models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class Message:
    """Normalized chat message."""

    role: str
    content: str


@dataclass(frozen=True)
class ToolCall:
    """Normalized tool call structure."""

    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ToolDefinition:
    """Normalized tool definition."""

    name: str
    description: str
    parameters: dict[str, Any]


@dataclass(frozen=True)
class CompletionResult:
    """Normalized completion result."""

    text: str
    tool_calls: list[ToolCall]
    usage: dict[str, Any]
    finish_reason: str | None
    latency_ms: int


class ProviderError(RuntimeError):
    """Error wrapper for provider failures."""

    def __init__(self, provider: str, status_code: int | None, response_body: str | None) -> None:
        truncated = response_body[:500] if response_body else None
        super().__init__(f"Provider {provider} error: {status_code}")
        self.provider = provider
        self.status_code = status_code
        self.response_body = truncated


class ProviderAdapter(Protocol):
    """Interface for provider adapters."""

    async def complete(
        self,
        messages: list[Message],
        model: str,
        tools: list[ToolDefinition] | None = None,
        response_format: dict[str, Any] | None = None,
    ) -> CompletionResult:
        """Execute a completion call."""

    async def health_check(self) -> bool:
        """Return True if provider responds to a minimal request."""
