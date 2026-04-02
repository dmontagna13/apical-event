"""FastAPI dependencies."""

from __future__ import annotations

import os
import socket
from pathlib import Path
from urllib.parse import urlparse

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


def get_apical_host() -> str:
    """Resolve the externally reachable host name or IP."""

    configured = os.environ.get("APICAL_HOST")
    if configured:
        if "://" in configured:
            parsed = urlparse(configured)
            if parsed.hostname:
                return parsed.hostname
        host = configured.split("/")[0]
        return host.split(":")[0]

    try:
        host = socket.gethostbyname(socket.gethostname())
    except socket.gaierror:
        host = "127.0.0.1"

    return host


def get_public_base_url() -> str:
    """Resolve the externally reachable base URL."""

    host = get_apical_host()
    port = os.environ.get("APICAL_PORT", str(DEFAULT_PORT))
    return f"http://{host}:{port}"


def get_providers(data_root: Path = Depends(get_data_root)) -> dict[str, ProviderConfig]:
    """Load provider configs from disk."""

    return load_providers(data_root)
