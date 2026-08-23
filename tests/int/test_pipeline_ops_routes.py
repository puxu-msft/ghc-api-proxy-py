"""The non-inference surface, on the chain that actually serves requests.

Until 2026-08-19 the new chain answered 404 to `/health/readiness` while the existing chain answered it — and the existing chain is the one two of the three entry points still run. A supervisor pointed at the new chain had nothing to ask.
"""

from types import SimpleNamespace
from typing import Any

import httpx2
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config.schema import ProxyConfig
from app.model_provider.types import ModelDescriptor, ModelEndpoint
from app.server.app_state import CHAIN_STATE_KEY
from app.server.routes.ops import router as ops_router
from app.server.routes.router import build_router


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


def client_for(ids: frozenset[str], config: ProxyConfig | None = None) -> httpx2.AsyncClient:
    app = FastAPI()
    app.include_router(ops_router)
    registry = StubRegistry({"ghc": StubProvider("ghc", ids)})
    # Only what the route under test reads; standing up a whole Chain would tie these to composition. `config` is left `None` for the routes that never touch it, so a route that starts reading it fails here rather than passing on a stub nobody meant to supply.
    setattr(app.state, CHAIN_STATE_KEY, SimpleNamespace(providers=registry, config=config))
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


@pytest.mark.asyncio
async def test_api_status_answers_from_the_same_judgement_as_readiness() -> None:
    """`api.md` ratifies both paths; they ask one question, so they must not be able to disagree.

    The chain this replaces answered `/api/status` from a readiness flag of its own, separate from the health endpoint — the arrangement where one fact gets two answers and they drift. Asserted as equality of the whole body rather than of a status field, because that is what forbids a second derivation from being added later.
    """
    for ids in (frozenset[str](), frozenset({"claude-opus-5"})):
        async with client_for(ids) as client:
            health = await client.get("/health/readiness")
            status = await client.get("/api/status")
        assert status.status_code == health.status_code
        assert status.json() == health.json()


@pytest.mark.asyncio
async def test_api_config_reports_the_snapshot_in_effect() -> None:
    """Not the file: five layers feed the snapshot, so the file alone cannot answer what is running."""
    config = ProxyConfig.model_validate({"server": {"port": 4199}, "graceful_cleanup_timeout": 7})
    async with client_for(frozenset({"m"}), config) as client:
        response = await client.get("/api/config")
    assert response.status_code == 200
    body = response.json()
    assert body["server"]["port"] == 4199
    assert body["graceful_cleanup_timeout"] == 7


@pytest.mark.asyncio
async def test_api_config_redacts_only_the_userinfo_of_the_proxy() -> None:
    """Which proxy is in use is the thing this is read to check; the password in it is not.

    Both directions are asserted. A proxy without credentials must come back untouched — otherwise "the secret is gone" would also be satisfied by blanking the field, and the test could not tell redaction from erasure.
    """
    with_credentials = ProxyConfig.model_validate({"proxy": "http://bob:hunter2@proxy.internal:8080"})
    async with client_for(frozenset({"m"}), with_credentials) as client:
        redacted = (await client.get("/api/config")).json()["proxy"]
    assert "hunter2" not in redacted
    assert "bob" not in redacted
    assert redacted == "http://***@proxy.internal:8080"

    plain = ProxyConfig.model_validate({"proxy": "http://proxy.internal:8080"})
    async with client_for(frozenset({"m"}), plain) as client:
        untouched = (await client.get("/api/config")).json()["proxy"]
    assert untouched == "http://proxy.internal:8080"


def test_the_ops_surface_is_mounted_on_the_router_production_builds() -> None:
    """Every test above mounts `ops_router` itself, so none of them can see whether anything else does.

    That gap is the shape this file was written for. Measured 2026-08-22: deleting `include_router(ops_router)` from `build_router` left all seven tests above green, while production went back to answering 404 on `/health/readiness` — the state the module docstring says was fixed on 2026-08-19. The mounting moved into `build_router` recently enough that its own docstring still explains why it used to live in the factory; nothing was watching it arrive.

    Asked through a request rather than by reading the route table, because the table cannot answer it: `include_router` leaves a single `_IncludedRouter` with `path=None` in `routes`, and the paths behind it do not appear even after the router is mounted on an app. Liveness and metrics are used because they are the two that answer without a chain.
    """
    app = FastAPI()
    app.include_router(build_router())
    client = TestClient(app)

    assert client.get("/health/liveness").status_code == 200
    assert client.get("/metrics").status_code == 200
