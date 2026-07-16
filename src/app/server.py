from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

import anyio
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app import __version__
from app.auth.providers import noninteractive_token_available
from app.config.paths import user_data_path
from app.config.settings import AppSettings
from app.history.consumer import HistoryConsumer
from app.history.store import HistoryStore
from app.observability.logging import setup_logging
from app.observability.telemetry import setup_metrics
from app.observability.tracing import setup_tracing
from app.pipeline.approval import ApprovalGate, ApprovalRejectedError
from app.routes import (
    anthropic_router,
    approval_router,
    azure_router,
    gemini_router,
    health_router,
    history_router,
    management_router,
)
from app.routes.metrics import router as metrics_router
from app.routes.openai import router as openai_router
from app.routes.responses_ws import router as responses_ws_router
from app.runtime import RuntimeState
from app.upstream.bootstrap import close_upstream_services, initialize_upstream_services


async def _approval_rejected_handler(
    _request: Request,
    error: Exception,
) -> JSONResponse:
    return JSONResponse(
        {"error": {"type": "approval_rejected", "message": str(error)}},
        status_code=403,
    )


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
            if settings.history.enabled:
                history_path = (
                    Path(settings.history.db_path)
                    if settings.history.db_path
                    else user_data_path() / "history.db"
                )
                runtime.history_store = HistoryStore(history_path)
                await runtime.history_store.start()
            runtime.approval_gate = ApprovalGate(
                enabled=settings.approval.enabled,
                timeout_seconds=settings.approval.timeout_seconds,
                websockets=(
                    runtime.history_store.websockets
                    if runtime.history_store is not None
                    else None
                ),
            )
            token_path = Path(settings.auth.token_file) if settings.auth.token_file else None
            has_noninteractive_token = await noninteractive_token_available(
                settings.auth.github_token,
                token_path,
            )
            if settings.upstream.type == "generic" or has_noninteractive_token:
                services = await initialize_upstream_services(runtime)
                if runtime.history_store is not None and runtime.anthropic_client is not None:
                    runtime.anthropic_client.history = HistoryConsumer(runtime.history_store)
                if runtime.anthropic_client is not None:
                    runtime.anthropic_client.approval_gate = runtime.approval_gate
                if services.copilot_tokens is not None:
                    task_group.start_soon(services.copilot_tokens.run_refresh_loop)
                if settings.model_refresh_interval > 0:
                    task_group.start_soon(
                        services.run_model_refresh_loop,
                        settings.model_refresh_interval,
                    )
            if (
                runtime.history_store is not None
                and settings.history.reaper_interval > 0
            ):
                task_group.start_soon(
                    runtime.history_store.run_reaper,
                    settings.history.reaper_interval,
                    settings.history.success_limit,
                    settings.history.failure_limit,
                )
            yield
        finally:
            if runtime.approval_gate is not None:
                await runtime.approval_gate.reject_all_pending("server shutting down")
                runtime.approval_gate = None
            if runtime.history_store is not None:
                await runtime.history_store.close()
                runtime.history_store = None
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
    app.add_exception_handler(ApprovalRejectedError, _approval_rejected_handler)
    setup_metrics()
    setup_tracing(app, enabled=resolved_settings.observability.tracing_enabled)
    app.include_router(anthropic_router)
    app.include_router(approval_router)
    app.include_router(azure_router)
    app.include_router(gemini_router)
    app.include_router(management_router)
    app.include_router(history_router)
    app.include_router(metrics_router)
    for prefix in ("", "/v1", "/openai/v1"):
        app.include_router(openai_router, prefix=prefix)
        app.include_router(responses_ws_router, prefix=prefix)
    app.include_router(health_router)
    return app