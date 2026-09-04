"""`refresh_catalogs` keeps one provider's failure from becoming every provider's failure.

Its own file because the defect it guards against is invisible from everywhere else. Catalogues load once, at start-up; nothing retries them (`run_model_refresh_loop` has no caller, `model_refresh_interval` no consumer on this chain); and a provider that never loaded surfaces only as `/health/readiness` answering 503 for the life of the process. An independent review found that a secondary provider with a stale token could take the **default** provider down with it, and which one got refreshed depended on `frozenset` iteration order.
"""

from types import SimpleNamespace
from typing import cast

import anyio
import pytest

import app.server.pipeline_app as pipeline_app_module
from app.config.schema import ProxyConfig
from app.core.chain import Chain
from app.model_provider.ghc_client.models import run_model_refresh_loop
from app.server.composition import refresh_catalogs
from app.server.pipeline_app import (
    _catalog_refresh_intervals,  # pyright: ignore[reportPrivateUsage]
    create_pipeline_app,
)


class _Provider:
    def __init__(self, name: str, *, fails: bool = False, log: list[str] | None = None) -> None:
        self.name = name
        self.refreshed = False
        self._fails = fails
        self._log = log

    async def refresh_catalog(self) -> bool:
        if self._log is not None:
            self._log.append(self.name)
        if self._fails:
            raise RuntimeError(f"{self.name}: no GitHub token")
        self.refreshed = True
        return True


class _Registry:
    def __init__(self, providers: dict[str, _Provider]) -> None:
        self._providers = providers

    @property
    def names(self) -> frozenset[str]:
        return frozenset(self._providers)

    def get(self, name: str) -> _Provider:
        return self._providers[name]


def _chain(providers: dict[str, _Provider]) -> Chain:
    # Only the one attribute `refresh_catalogs` reads; a whole `Chain` would drag composition in.
    return cast(Chain, SimpleNamespace(providers=_Registry(providers)))


@pytest.mark.asyncio
async def test_a_failing_provider_does_not_stop_the_rest() -> None:
    """A stale token on one account must not decide whether another account gets loaded.

    `A` sorts first and raises. Before the guard existed the loop ended there, `B` — the default in the deployment this models — kept an empty catalogue, and readiness answered 503 while the account serving nearly all traffic was healthy.
    """
    providers = {"A": _Provider("A", fails=True), "B": _Provider("B")}
    await refresh_catalogs(_chain(providers))
    assert providers["B"].refreshed is True
    assert providers["A"].refreshed is False


@pytest.mark.asyncio
async def test_every_provider_is_attempted_even_when_all_of_them_fail() -> None:
    """The control for the test above, which a `try` around the whole loop would also satisfy."""
    log: list[str] = []
    providers = {
        "A": _Provider("A", fails=True, log=log),
        "B": _Provider("B", fails=True, log=log),
    }
    await refresh_catalogs(_chain(providers))
    assert log == ["A", "B"]


@pytest.mark.asyncio
async def test_providers_are_refreshed_in_a_deterministic_order() -> None:
    """`names` is a `frozenset`, so its own order comes from hashing rather than from configuration.

    The guard is what makes order stop mattering for correctness. This is about reproducibility: a start-up sequence that varies between runs of an unchanged deployment is one nobody can reason about from a log.
    """
    log: list[str] = []
    providers = {name: _Provider(name, log=log) for name in ("zeta", "alpha", "mid")}
    await refresh_catalogs(_chain(providers))
    assert log == ["alpha", "mid", "zeta"]


def test_only_positive_dynamic_provider_intervals_create_refresh_jobs() -> None:
    config = ProxyConfig.model_validate(
        {
            "model_providers": {
                "active": {"type": "github_copilot", "model_refresh_interval": 17},
                "disabled": {"type": "github_copilot", "model_refresh_interval": 0},
                "static": {"type": "codebuddy"},
            },
            "default_model_provider": "active",
        }
    )
    chain = cast(Chain, SimpleNamespace(config=config))

    assert _catalog_refresh_intervals(chain) == (("active", 17),)


@pytest.mark.asyncio
async def test_pipeline_lifespan_starts_and_cancels_the_configured_refresh_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entered = anyio.Event()
    cancelled = anyio.Event()
    calls: list[tuple[str, int]] = []

    class _Tokenization:
        def __init__(self) -> None:
            self.loaded = False
            self.flushed = False

        async def load(self) -> None:
            self.loaded = True

        async def flush(self) -> None:
            self.flushed = True

        async def run_periodic_flush(self, _interval: float) -> None:
            await anyio.sleep_forever()

    async def unavailable_at_startup(_chain: Chain) -> None:
        raise RuntimeError("startup catalog unavailable")

    async def controlled_refresh(_chain: Chain, name: str, interval: int) -> None:
        calls.append((name, interval))
        entered.set()
        try:
            await anyio.sleep_forever()
        finally:
            cancelled.set()

    def no_footer(_active: object, _capabilities: object) -> None:
        return None

    monkeypatch.setattr(pipeline_app_module, "refresh_catalogs", unavailable_at_startup)
    monkeypatch.setattr(pipeline_app_module, "_run_catalog_refresh", controlled_refresh)
    monkeypatch.setattr(pipeline_app_module, "footer_tui_or_none", no_footer)
    config = ProxyConfig.model_validate(
        {
            "model_providers": {
                "active": {"type": "github_copilot", "model_refresh_interval": 17},
                "disabled": {"type": "github_copilot", "model_refresh_interval": 0},
                "static": {"type": "codebuddy"},
            },
            "default_model_provider": "active",
        }
    )
    tokenization = _Tokenization()
    chain = cast(
        Chain,
        SimpleNamespace(
            config=config,
            providers=_Registry({"active": _Provider("active")}),
            tokenization=tokenization,
            active_requests=object(),
            capabilities=object(),
        ),
    )
    app = create_pipeline_app(chain)

    with anyio.fail_after(2):
        async with app.router.lifespan_context(app):
            await entered.wait()

    assert calls == [("active", 17)]
    assert tokenization.loaded is True
    assert tokenization.flushed is True
    assert cancelled.is_set()


@pytest.mark.asyncio
async def test_periodic_refresh_reports_one_failure_and_keeps_running() -> None:
    class StopLoop(Exception):
        pass

    sleeps: list[float] = []
    calls = 0
    errors: list[Exception] = []

    async def sleep(interval: float) -> None:
        sleeps.append(interval)
        if len(sleeps) == 3:
            raise StopLoop

    async def refresh() -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("catalog unavailable")

    with pytest.raises(StopLoop):
        await run_model_refresh_loop(
            refresh,
            interval_seconds=17,
            on_error=errors.append,
            sleep=sleep,
        )

    assert sleeps == [17, 17, 17]
    assert calls == 2
    assert len(errors) == 1
    assert str(errors[0]) == "catalog unavailable"


@pytest.mark.asyncio
async def test_periodic_refresh_cancels_an_inflight_refresh() -> None:
    entered = anyio.Event()
    cancelled = anyio.Event()

    async def no_sleep(_interval: float) -> None:
        return None

    async def refresh() -> None:
        entered.set()
        try:
            await anyio.sleep_forever()
        finally:
            cancelled.set()

    async def run() -> None:
        await run_model_refresh_loop(
            refresh,
            interval_seconds=17,
            on_error=lambda _error: None,
            sleep=no_sleep,
        )

    async with anyio.create_task_group() as tasks:
        tasks.start_soon(run)
        await entered.wait()
        tasks.cancel_scope.cancel()

    assert cancelled.is_set()
