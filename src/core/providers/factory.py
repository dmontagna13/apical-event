"""Provider adapter factory."""

from __future__ import annotations

from core.config import ProviderConfig

from .anthropic import AnthropicAdapter
from .deepseek import DeepSeekAdapter
from .gemini import GeminiAdapter
from .openai import OpenAIAdapter


def get_adapter(provider_key: str, provider_config: ProviderConfig):
    """Construct a provider adapter from config."""

    if provider_key == "openai":
        return OpenAIAdapter(
            base_url=provider_config.base_url or "",
            api_key=provider_config.api_key or "",
            default_model=provider_config.default_model,
        )
    if provider_key == "nscale":
        return OpenAIAdapter(
            base_url=provider_config.base_url or "",
            api_key=provider_config.api_key or "",
            default_model=provider_config.default_model,
        )
    if provider_key == "gemini":
        return GeminiAdapter(
            base_url=provider_config.base_url or "",
            api_key=provider_config.api_key or "",
            default_model=provider_config.default_model,
        )
    if provider_key == "anthropic":
        return AnthropicAdapter(
            base_url=provider_config.base_url or "",
            api_key=provider_config.api_key or "",
            default_model=provider_config.default_model,
        )
    if provider_key == "deepseek":
        return DeepSeekAdapter(
            base_url=provider_config.base_url or "",
            api_key=provider_config.api_key or "",
            default_model=provider_config.default_model,
        )

    raise ValueError(f"Unknown provider key: {provider_key}")
