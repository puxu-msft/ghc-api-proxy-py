"""`refresh_catalogs` keeps one provider's failure from becoming every provider's failure.

Its own file because the defect it guards against is invisible from everywhere else. Catalogues load once, at start-up; nothing retries them (`run_model_refresh_loop` has no caller, `model_refresh_interval` no consumer on this chain); and a provider that never loaded surfaces only as `/health/readiness` answering 503 for the life of the process. An independent review found that a secondary provider with a stale token could take the **default** provider down with it, and which one got refreshed depended on `frozenset` iteration order.
"""

from types import SimpleNamespace
from typing import cast

import pytest

from app.core.chain import Chain
from app.server.composition import refresh_catalogs


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
