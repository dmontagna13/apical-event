"""Config module tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from core.config import (
    delete_preset,
    is_first_run,
    load_last_roll_call,
    load_presets,
    load_providers,
    resolve_api_key,
    save_last_roll_call,
    save_preset,
    save_providers,
)
from core.config.providers import ProviderConfig
from core.schemas import RoleAssignment, RollCall


def _write_providers_yaml(path: Path, providers: dict[str, dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump({"providers": providers}, sort_keys=False))


def test_load_providers_returns_models(tmp_path: Path) -> None:
    providers_path = tmp_path / "config" / "providers.yaml"
    _write_providers_yaml(
        providers_path,
        {
            "openai": {
                "display_name": "OpenAI",
                "base_url": "https://api.openai.com/v1",
                "api_key_env": "OPENAI_API_KEY",
                "api_key": None,
                "default_model": "gpt-4o",
                "available_models": ["gpt-4o"],
                "supports_function_calling": True,
                "supports_structured_output": True,
                "max_context_tokens": 128000,
            }
        },
    )

    providers = load_providers(tmp_path)
    assert "openai" in providers
    assert isinstance(providers["openai"], ProviderConfig)


def test_resolve_api_key_env_priority(monkeypatch: pytest.MonkeyPatch) -> None:
    config = ProviderConfig(
        display_name="Test",
        base_url=None,
        api_key_env="TEST_KEY",
        api_key="inline",
        default_model=None,
        available_models=[],
        supports_function_calling=True,
        supports_structured_output=True,
        max_context_tokens=1,
    )
    monkeypatch.setenv("TEST_KEY", "from_env")
    assert resolve_api_key(config) == "from_env"


def test_resolve_api_key_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    config = ProviderConfig(
        display_name="Test",
        base_url=None,
        api_key_env="TEST_KEY",
        api_key="inline",
        default_model=None,
        available_models=[],
        supports_function_calling=True,
        supports_structured_output=True,
        max_context_tokens=1,
    )
    monkeypatch.delenv("TEST_KEY", raising=False)
    assert resolve_api_key(config) == "inline"


def test_resolve_api_key_none(monkeypatch: pytest.MonkeyPatch) -> None:
    config = ProviderConfig(
        display_name="Test",
        base_url=None,
        api_key_env="TEST_KEY",
        api_key=None,
        default_model=None,
        available_models=[],
        supports_function_calling=True,
        supports_structured_output=True,
        max_context_tokens=1,
    )
    monkeypatch.delenv("TEST_KEY", raising=False)
    assert resolve_api_key(config) is None


def test_is_first_run_missing_file(tmp_path: Path) -> None:
    assert is_first_run(tmp_path) is True


def test_is_first_run_no_keys(tmp_path: Path) -> None:
    providers_path = tmp_path / "config" / "providers.yaml"
    _write_providers_yaml(
        providers_path,
        {
            "openai": {
                "display_name": "OpenAI",
                "base_url": "https://api.openai.com/v1",
                "api_key_env": "OPENAI_API_KEY",
                "api_key": None,
                "default_model": "gpt-4o",
                "available_models": ["gpt-4o"],
                "supports_function_calling": True,
                "supports_structured_output": True,
                "max_context_tokens": 128000,
            }
        },
    )
    assert is_first_run(tmp_path) is True


def test_is_first_run_with_key(tmp_path: Path) -> None:
    providers_path = tmp_path / "config" / "providers.yaml"
    _write_providers_yaml(
        providers_path,
        {
            "openai": {
                "display_name": "OpenAI",
                "base_url": "https://api.openai.com/v1",
                "api_key_env": None,
                "api_key": "inline",
                "default_model": "gpt-4o",
                "available_models": ["gpt-4o"],
                "supports_function_calling": True,
                "supports_structured_output": True,
                "max_context_tokens": 128000,
            }
        },
    )
    assert is_first_run(tmp_path) is False


def test_save_providers_atomic(tmp_path: Path) -> None:
    providers = {
        "openai": ProviderConfig(
            display_name="OpenAI",
            base_url="https://api.openai.com/v1",
            api_key_env="OPENAI_API_KEY",
            api_key=None,
            default_model="gpt-4o",
            available_models=["gpt-4o"],
            supports_function_calling=True,
            supports_structured_output=True,
            max_context_tokens=128000,
        )
    }
    save_providers(tmp_path, providers)
    providers_path = tmp_path / "config" / "providers.yaml"
    tmp_path_file = providers_path.with_suffix(providers_path.suffix + ".tmp")
    assert providers_path.exists()
    assert not tmp_path_file.exists()


def test_load_providers_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_providers(tmp_path)


def test_load_providers_corrupt_yaml(tmp_path: Path) -> None:
    providers_path = tmp_path / "config" / "providers.yaml"
    providers_path.parent.mkdir(parents=True, exist_ok=True)
    providers_path.write_text("providers: [\n")
    with pytest.raises(ValueError, match="Invalid YAML"):
        load_providers(tmp_path)


def test_load_last_roll_call_missing(tmp_path: Path) -> None:
    assert load_last_roll_call(tmp_path) is None


def test_last_roll_call_round_trip(tmp_path: Path) -> None:
    roll_call = RollCall(
        assignments=[RoleAssignment(role_id="RG-FAC", provider="openai", model="gpt")]
    )
    save_last_roll_call(tmp_path, roll_call)
    loaded = load_last_roll_call(tmp_path)
    assert loaded is not None
    assert loaded.model_dump(mode="json") == roll_call.model_dump(mode="json")


def test_preset_round_trip(tmp_path: Path) -> None:
    roll_call = RollCall(
        assignments=[RoleAssignment(role_id="RG-FAC", provider="openai", model="gpt")]
    )
    save_preset(tmp_path, "preset-1", roll_call)
    presets = load_presets(tmp_path)
    assert len(presets) == 1
    assert presets[0].name == "preset-1"
    assert presets[0].assignments[0].role_id == "RG-FAC"

    assert delete_preset(tmp_path, "preset-1") is True
    assert load_presets(tmp_path) == []
    assert delete_preset(tmp_path, "missing") is False


def test_presets_file_structure(tmp_path: Path) -> None:
    roll_call = RollCall(
        assignments=[RoleAssignment(role_id="RG-FAC", provider="openai", model="gpt")]
    )
    save_preset(tmp_path, "preset-1", roll_call)
    path = tmp_path / "config" / "roll_call_presets.json"
    data = json.loads(path.read_text())
    assert "presets" in data
