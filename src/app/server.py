from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import anyio
from fastapi import FastAPI

from app import __version__
from app.config.settings import AppSettings
from app.observability.logging import setup_logging
from app.routes import health_router
from app.runtime import RuntimeState


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncGenerator[None]:
    runtime: RuntimeState = app.state.runtime
    settings = runtime.settings
    setup_logging(
        log_format=settings.observability.log_format,
        log_level=settings.observability.log_level,
    )

    async with anyio.create_task_group() as task_group:
        runtime.background_task_group = task_group
        try:
            yield
        finally:
            task_group.cancel_scope.cancel()
            runtime.background_task_group = None


def create_app(settings: AppSettings | None = None) -> FastAPI:
    resolved_settings = settings or AppSettings()
    app = FastAPI(
        title="ghc-api-proxy",
        version=__version__,
        lifespan=_lifespan,
    )
    app.state.runtime = RuntimeState(settings=resolved_settings)
    app.include_router(health_router)
    return app