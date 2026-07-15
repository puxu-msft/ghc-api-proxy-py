from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

import anyio
from fastapi import FastAPI

from app import __version__
from app.auth.providers import noninteractive_token_available
from app.config.settings import AppSettings
from app.observability.logging import setup_logging
from app.routes import anthropic_router, health_router, management_router
from app.routes.openai import router as openai_router
from app.routes.responses_ws import router as responses_ws_router
from app.runtime import RuntimeState
from app.upstream.bootstrap import close_upstream_services, initialize_upstream_services


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
            token_path = Path(settings.auth.token_file) if settings.auth.token_file else None
            has_noninteractive_token = await noninteractive_token_available(
                settings.auth.github_token,
                token_path,
            )
            if settings.upstream.type == "generic" or has_noninteractive_token:
                services = await initialize_upstream_services(runtime)
                if services.copilot_tokens is not None:
                    task_group.start_soon(services.copilot_tokens.run_refresh_loop)
                if settings.model_refresh_interval > 0:
                    task_group.start_soon(
                        services.run_model_refresh_loop,
                        settings.model_refresh_interval,
                    )
            yield
        finally:
            await close_upstream_services(runtime)
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
    app.include_router(anthropic_router)
    app.include_router(management_router)
    for prefix in ("", "/v1", "/openai/v1"):
        app.include_router(openai_router, prefix=prefix)
        app.include_router(responses_ws_router, prefix=prefix)
    app.include_router(health_router)
    return app