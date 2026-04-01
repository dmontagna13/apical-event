"""DeepSeek adapter (OpenAI-compatible)."""

from __future__ import annotations

from .openai import OpenAIAdapter


class DeepSeekAdapter(OpenAIAdapter):
    """DeepSeek adapter using OpenAI-compatible API."""

    provider_name = "deepseek"
