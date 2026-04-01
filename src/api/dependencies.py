"""FastAPI dependencies."""

from __future__ import annotations

import os
import socket
from pathlib import Path

from fastapi import Depends

from core.config import ProviderConfig, load_providers
from core.schemas.constants import DEFAULT_PORT


def get_data_root() -> Path:
    """Resolve data root from environment."""

    env_value = os.environ.get("APICAL_DATA")
    if env_value:
        return Path(env_value)
    docker_data = Path("/data")
    if docker_data.exists():
        return docker_data
    return Path("./data")


def get_public_base_url() -> str:
    """Resolve the externally reachable base URL."""

    configured = os.environ.get("APICAL_HOST")
    if configured:
        if configured.startswith(("http://", "https://")):
            return configured.rstrip("/")
        port = os.environ.get("APICAL_PORT", str(DEFAULT_PORT))
        if ":" in configured:
            return f"http://{configured}".rstrip("/")
        return f"http://{configured}:{port}"

    try:
        host = socket.gethostbyname(socket.gethostname())
    except socket.gaierror:
        host = "localhost"

    port = os.environ.get("APICAL_PORT", str(DEFAULT_PORT))
    return f"http://{host}:{port}"


def get_providers(data_root: Path = Depends(get_data_root)) -> dict[str, ProviderConfig]:
    """Load provider configs from disk."""

    return load_providers(data_root)
