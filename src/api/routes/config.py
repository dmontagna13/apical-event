"""Provider configuration endpoints."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.dependencies import get_data_root, get_providers
from api.routes.sessions import ApiError
from core.config import (
    ProviderConfig,
    load_presets,
    load_providers,
    resolve_api_key,
    save_preset,
    save_providers,
)
from core.providers import ProviderError, get_adapter
from core.schemas import RoleAssignment, RollCall
from core.schemas.enums import ErrorCode

router = APIRouter()
logger = logging.getLogger(__name__)


class PresetPayload(BaseModel):
    """Payload for creating or updating a roll call preset."""

    name: str
    assignments: list[RoleAssignment]


@router.get("/api/config/providers")
def list_providers(providers: dict[str, ProviderConfig] = Depends(get_providers)) -> dict:
    """List provider configs with connectivity info."""

    response = {}
    for key, config in providers.items():
        response[key] = {
            **config.model_dump(mode="json"),
            "has_api_key": resolve_api_key(config) is not None,
        }
    return {"providers": response}


@router.put("/api/config/providers/{provider_key}")
def update_provider(
    provider_key: str,
    config: ProviderConfig,
    data_root: Path = Depends(get_data_root),
) -> dict:
    """Update a provider configuration."""

    providers = load_providers(data_root)
    providers[provider_key] = config
    save_providers(data_root, providers)
    return {"ok": True}


@router.get("/api/config/providers/{provider_key}/models")
async def list_provider_models(
    provider_key: str,
    data_root: Path = Depends(get_data_root),
) -> dict:
    """List available models for a provider."""

    providers = load_providers(data_root)
    config = providers.get(provider_key)
    if not config:
        raise ApiError(404, ErrorCode.NOT_FOUND, "Provider not found")

    api_key = resolve_api_key(config)
    if not api_key:
        return {"models": config.available_models}

    adapter = get_adapter(provider_key, config.model_copy(update={"api_key": api_key}))
    try:
        models = await adapter.list_models()
    except ProviderError as exc:
        logger.warning("Model listing failed for %s: %s", provider_key, exc)
        models = None

    if models:
        return {"models": models}
    return {"models": config.available_models}


@router.post("/api/config/providers/{provider_key}/test")
async def test_provider(
    provider_key: str,
    providers: dict[str, ProviderConfig] = Depends(get_providers),
) -> dict:
    """Test provider connectivity."""

    config = providers.get(provider_key)
    if not config:
        raise ApiError(404, ErrorCode.NOT_FOUND, "Provider not found")

    api_key = resolve_api_key(config)
    if not api_key:
        return {"ok": False, "error": "Missing API key"}

    adapter = get_adapter(provider_key, config.model_copy(update={"api_key": api_key}))
    try:
        ok = await adapter.health_check()
    except ProviderError as exc:
        return {"ok": False, "error": exc.response_body or "Provider error"}

    return {"ok": ok}


@router.get("/api/config/presets")
def list_presets(data_root: Path = Depends(get_data_root)) -> dict:
    """List stored roll call presets."""

    presets = load_presets(data_root)
    return {"presets": [preset.model_dump(mode="json") for preset in presets]}


@router.post("/api/config/presets")
def save_preset_route(
    payload: PresetPayload,
    data_root: Path = Depends(get_data_root),
) -> dict:
    """Create or update a named roll call preset."""

    roll_call = RollCall(assignments=payload.assignments)
    save_preset(data_root, payload.name, roll_call)
    return {"ok": True}
