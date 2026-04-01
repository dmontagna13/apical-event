"""FastAPI dependencies."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import Depends

from core.config import ProviderConfig, load_providers


def get_data_root() -> Path:
    """Resolve data root from environment."""

    return Path(os.environ.get("APICAL_DATA", "./data"))


def get_providers(data_root: Path = Depends(get_data_root)) -> dict[str, ProviderConfig]:
    """Load provider configs from disk."""

    return load_providers(data_root)
