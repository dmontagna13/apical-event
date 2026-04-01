"""FastAPI dependencies."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import Depends

from core.config import ProviderConfig, load_providers


def get_data_root() -> Path:
    """Resolve data root from environment."""

    env_value = os.environ.get("APICAL_DATA")
    if env_value:
        return Path(env_value)
    docker_data = Path("/data")
    if docker_data.exists():
        return docker_data
    return Path("./data")


def get_providers(data_root: Path = Depends(get_data_root)) -> dict[str, ProviderConfig]:
    """Load provider configs from disk."""

    return load_providers(data_root)
