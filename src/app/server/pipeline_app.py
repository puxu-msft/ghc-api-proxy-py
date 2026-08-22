"""The ASGI application: build it, mount the routes, run its lifespan.

The endpoints themselves are `app.server.routes` — the name `docs/.human-controlled/module-org.md` ratified, which the code had never had until 2026-08-22. What is left here is assembly.

Separate from `app_factory`, which builds the chain no entry point reaches. Mounting both would give one path two owners.
"""

import os
from collections.abc import AsyncGenerator
from contextlib import ExitStack, asynccontextmanager
from importlib.metadata import PackageNotFoundError, version

import anyio
from fastapi import FastAPI

from app.core.chain import Chain
from app.observability.logging import get_logger
from app.observability.tui import footer_tui_or_none
from app.server.admission import InFlightLimit
from app.server.app_state import chain_of_app, set_chain
from app.server.composition import refresh_catalogs
from app.server.routes.router import build_router

# What the calibrator has learnt is only worth keeping if it survives the process.
# Not configurable: `config.example.yaml` has no `tokenization` section to put it in.
TOKENIZATION_FLUSH_SECONDS = 5.0




def create_pipeline_app(chain: Chain) -> FastAPI:
    app = FastAPI(title="ghc-api-proxy", lifespan=_lifespan)
    set_chain(app, chain)
    app.include_router(build_router())
    # Outermost, so the bound counts a request from the moment it arrives rather than from the moment routing finishes. Over the limit a request waits; it is never refused and its connection is never closed — see `app.server.admission`.
    app.add_middleware(
        InFlightLimit,
        max_inflight=chain.config.proactive_rate_limiter.max_inflight,
    )
    return app


def _version() -> str:
    """The installed version, or `unknown` when there is no installed distribution to ask.

    Never raises. Running from a source tree that was never installed is an ordinary way to run this, and a banner line is the last thing that should be able to stop the server from starting — which it did, until the lookup was given the wrong distribution name and took the whole lifespan down with it.
    """
    try:
        return version("app")
    except PackageNotFoundError:
        return "unknown"


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Carry the calibrator's state across restarts.

    Without this the `local` token counter starts from nothing every time and throws away everything it learns, which makes its estimates worse the more the process is restarted — and says nothing about it, because an estimate is still returned.
    """
    chain = chain_of_app(app)
    logger = get_logger()
    logger.info(f"ghc-api-proxy v{_version()} pid={os.getpid()}", status="ok")
    # Attempted before accepting, because routing fails closed on capability: a request arriving first would otherwise be refused with a message saying the model does not exist.
    #
    # Not fatal, though. A supervised service that cannot reach upstream at boot — no credential yet, network not up — must still start and say it is not ready, which is what `/health/readiness` answers from the same empty catalog. Raising here instead turns a degraded start into a service that never comes up at all, and the socket systemd already opened would hold the client's connection open against a process that is dying.
    try:
        await refresh_catalogs(chain)
    except Exception as error:
        logger.warning(f"model catalog unavailable, serving as not-ready: {error}", status="fail")
    else:
        provider = chain.providers.get(chain.providers.default_name)
        logger.info(f"{len(provider.available_ids)} models available from {chain.providers.default_name}", status="ok")
    await chain.tokenization.load()
    # Probed, not configured: whether a live footer belongs on this stream is a fact about where the output goes, and the process can see that for itself. Nothing is logged when it comes back unsupported — a pipe or a CI job is the normal case, not a degradation worth a line in everybody's log.
    tui = footer_tui_or_none(chain.active_requests, chain.capabilities)
    async with anyio.create_task_group() as flushing:
        flushing.start_soon(chain.tokenization.run_periodic_flush, TOKENIZATION_FLUSH_SECONDS)
        try:
            with ExitStack() as terminal:
                if tui is not None:
                    terminal.enter_context(tui.activate())
                yield
        finally:
            # The periodic flush cannot be relied on to have caught the last change.
            await chain.tokenization.flush()
            flushing.cancel_scope.cancel()
