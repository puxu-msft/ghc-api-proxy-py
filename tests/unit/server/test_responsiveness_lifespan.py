from types import SimpleNamespace
from typing import cast

import anyio
import pytest
from anyio.lowlevel import checkpoint

import app.server.pipeline_app as pipeline_app_module
from app.config.schema import ProxyConfig
from app.core.chain import Chain
from app.server.pipeline_app import create_pipeline_app


class _Tokenization:
    def __init__(self) -> None:
        self.loaded = False
        self.flushed = False
        self.periodic_cancelled = anyio.Event()

    async def load(self) -> None:
        self.loaded = True

    async def flush(self) -> None:
        self.flushed = True

    async def run_periodic_flush(self, _interval: float) -> None:
        never_release = anyio.Event()
        try:
            await never_release.wait()
        finally:
            self.periodic_cancelled.set()


@pytest.mark.asyncio
async def test_headless_lifespan_starts_one_heartbeat_and_cancels_it_in_finally(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    heartbeat_entered = anyio.Event()
    heartbeat_cancelled = anyio.Event()
    never_release = anyio.Event()
    heartbeat_starts = 0
    footer_probes = 0

    async def unavailable_at_startup(_chain: Chain) -> None:
        raise RuntimeError("startup catalog unavailable")

    async def controlled_heartbeat() -> None:
        nonlocal heartbeat_starts
        heartbeat_starts += 1
        heartbeat_entered.set()
        try:
            await never_release.wait()
        finally:
            heartbeat_cancelled.set()

    def headless_footer(_active: object, _capabilities: object) -> None:
        nonlocal footer_probes
        footer_probes += 1
        return None

    monkeypatch.setattr(pipeline_app_module, "refresh_catalogs", unavailable_at_startup)
    monkeypatch.setattr(pipeline_app_module, "monitor_event_loop", controlled_heartbeat)
    monkeypatch.setattr(pipeline_app_module, "footer_tui_or_none", headless_footer)
    tokenization = _Tokenization()
    chain = cast(
        Chain,
        SimpleNamespace(
            config=ProxyConfig(),
            providers=object(),
            tokenization=tokenization,
            active_requests=object(),
            capabilities=object(),
        ),
    )
    app = create_pipeline_app(chain)

    with anyio.fail_after(2):
        async with app.router.lifespan_context(app):
            await heartbeat_entered.wait()
            await checkpoint()
            assert heartbeat_starts == 1
            assert footer_probes == 1
            assert tokenization.loaded is True
            assert heartbeat_cancelled.is_set() is False

    assert heartbeat_cancelled.is_set()
    assert tokenization.periodic_cancelled.is_set()
    assert tokenization.flushed is True
