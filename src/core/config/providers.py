"""Provider configuration I/O."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field


class ProviderConfig(BaseModel):
    """Provider configuration loaded from providers.yaml."""

    display_name: str
    base_url: Optional[str]
    api_key_env: Optional[str]
    api_key: Optional[str]
    default_model: Optional[str]
    available_models: list[str] = Field(default_factory=list)
    supports_function_calling: bool
    supports_structured_output: bool
    max_context_tokens: int


def _providers_path(data_root: Path) -> Path:
    return data_root / "config" / "providers.yaml"


def load_providers(data_root: Path) -> dict[str, ProviderConfig]:
    """Load provider configs from YAML."""

    path = _providers_path(data_root)
    if not path.exists():
        raise FileNotFoundError(f"providers.yaml not found at {path}")

    try:
        data = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:  # pragma: no cover - exercised via tests
        raise ValueError("Invalid YAML in providers.yaml") from exc

    if (
        not isinstance(data, dict)
        or "providers" not in data
        or not isinstance(data["providers"], dict)
    ):
        raise ValueError("providers.yaml must contain a top-level 'providers' mapping")

    providers: dict[str, ProviderConfig] = {}
    for key, value in data["providers"].items():
        providers[key] = ProviderConfig.model_validate(value)

    return providers


def save_providers(data_root: Path, providers: dict[str, ProviderConfig]) -> None:
    """Save provider configs to YAML atomically."""

    path = _providers_path(data_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"providers": {key: cfg.model_dump() for key, cfg in providers.items()}}
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(yaml.safe_dump(payload, sort_keys=False))
    os.replace(tmp_path, path)


def resolve_api_key(config: ProviderConfig) -> Optional[str]:
    """Resolve API key from env var or inline config."""

    if config.api_key_env:
        env_value = os.environ.get(config.api_key_env)
        if env_value:
            return env_value
    if config.api_key:
        return config.api_key
    return None


def is_first_run(data_root: Path) -> bool:
    """Return True if no providers are configured with API keys."""

    path = _providers_path(data_root)
    if not path.exists():
        return True

    providers = load_providers(data_root)
    for config in providers.values():
        if resolve_api_key(config):
            return False
    return True
