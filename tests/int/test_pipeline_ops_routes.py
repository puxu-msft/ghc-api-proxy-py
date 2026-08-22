"""The non-inference surface, on the chain that actually serves requests.

Until 2026-08-19 the new chain answered 404 to `/health/readiness` while the existing chain answered it — and the existing chain is the one two of the three entry points still run. A supervisor pointed at the new chain had nothing to ask.
"""

from types import SimpleNamespace
from typing import Any

import httpx2
import pytest
from fastapi import FastAPI

from app.model_provider.types import ModelDescriptor, ModelEndpoint
from app.server.app_state import CHAIN_STATE_KEY
from app.server.routes.ops import router as ops_router


class StubProvider:
    def __init__(self, name: str, ids: frozenset[str]) -> None:
        self.name = name
        self._ids = ids

    @property
    def available_ids(self) -> frozenset[str]:
        return self._ids

    def describe(self, model_id: str) -> ModelDescriptor | None:
        if model_id not in self._ids:
            return None
        return ModelDescriptor(id=model_id, endpoints=frozenset({ModelEndpoint.ANTHROPIC_MESSAGES}))

    async def refresh_catalog(self) -> bool:
        return False

    async def send(self, *args: Any, **kwargs: Any) -> httpx2.Response:
        raise NotImplementedError

    async def count_tokens(self, *args: Any, **kwargs: Any) -> httpx2.Response:
        raise NotImplementedError


class StubRegistry:
    def __init__(self, providers: dict[str, StubProvider]) -> None:
        self._providers = providers

    @property
    def names(self) -> frozenset[str]:
        return frozenset(self._providers)

    @property
    def default(self) -> StubProvider:
        return next(iter(self._providers.values()))

    def get(self, name: str) -> StubProvider:
        return self._providers[name]


def client_for(ids: frozenset[str]) -> httpx2.AsyncClient:
    app = FastAPI()
    app.include_router(ops_router)
    registry = StubRegistry({"ghc": StubProvider("ghc", ids)})
    # Only `providers` is read here; standing up a whole Chain would tie these to composition.
    setattr(app.state, CHAIN_STATE_KEY, SimpleNamespace(providers=registry))
    return httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), base_url="http://t")


@pytest.mark.asyncio
async def test_liveness_says_nothing_about_readiness() -> None:
    """Separate on purpose: a process that is up but cannot route is alive and not ready."""
    async with client_for(frozenset()) as client:
        response = await client.get("/health/liveness")
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


@pytest.mark.asyncio
async def test_an_empty_catalog_is_not_ready() -> None:
    """The direction that matters. Routing fails closed on capability, so with no catalog every
    request is refused — and a 200 here is how a supervisor gets told to send traffic anyway."""
    async with client_for(frozenset()) as client:
        response = await client.get("/health/readiness")
    assert response.status_code == 503
    assert response.json()["status"] == "uninitialized"


@pytest.mark.asyncio
async def test_a_populated_catalog_is_ready() -> None:
    async with client_for(frozenset({"claude-opus-5"})) as client:
        response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "providers": {"ghc": {"models": 1}}}


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/models", "/v1/models", "/openai/v1/models"])
async def test_the_model_list_is_the_catalog_routing_consults(path: str) -> None:
    """Listing anything routing would refuse would send a client after a model it cannot have."""
    async with client_for(frozenset({"claude-opus-5", "gpt-5.6-terra"})) as client:
        response = await client.get(path)
    assert response.status_code == 200
    assert [entry["id"] for entry in response.json()["data"]] == ["claude-opus-5", "gpt-5.6-terra"]


@pytest.mark.asyncio
async def test_metrics_are_served() -> None:
    async with client_for(frozenset({"m"})) as client:
        response = await client.get("/metrics")
    assert response.status_code == 200
    assert b"python_gc_objects_collected_total" in response.content
