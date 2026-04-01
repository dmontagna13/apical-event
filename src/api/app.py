"""FastAPI application factory."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from api.dependencies import get_data_root
from api.routes import config, health, sessions
from api.routes.sessions import ApiError, _error_payload
from api.websocket.handler import websocket_endpoint
from core.schemas.enums import ErrorCode

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """Create the FastAPI application."""

    app = FastAPI()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost", "http://127.0.0.1"],
        allow_origin_regex=r"^http://localhost(:\d+)?$|^http://127\.0\.0\.1(:\d+)?$",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(sessions.router)
    app.include_router(config.router)

    app.add_api_websocket_route("/ws/session/{session_id}", websocket_endpoint)

    @app.exception_handler(ApiError)
    async def api_error_handler(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_payload(exc.code, exc.message, exc.details),
        )

    @app.exception_handler(FileNotFoundError)
    async def not_found_handler(_: Request, exc: FileNotFoundError) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content=_error_payload(ErrorCode.NOT_FOUND, str(exc)),
        )

    static_dir = Path("/app/static")
    if static_dir.exists():
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

    def resolve_default_providers_path() -> Path | None:
        candidates = [
            Path("/app/config/providers.default.yaml"),
            Path(__file__).resolve().parents[2] / "config" / "providers.default.yaml",
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return None

    def ensure_providers_file(data_root: Path) -> None:
        providers_path = data_root / "config" / "providers.yaml"
        if providers_path.exists():
            return
        providers_path.parent.mkdir(parents=True, exist_ok=True)
        template_path = resolve_default_providers_path()
        if not template_path:
            logger.warning(
                "providers.default.yaml not found; skipping bootstrap",
                extra={"data_root": str(data_root)},
            )
            return
        shutil.copyfile(template_path, providers_path)
        logger.info(
            "Created providers.yaml from template",
            extra={"providers_path": str(providers_path)},
        )

    @app.on_event("startup")
    def log_startup() -> None:
        data_root = get_data_root()
        ensure_providers_file(data_root)
        logger.info("Starting Apical-Event", extra={"data_root": str(data_root)})

    return app
