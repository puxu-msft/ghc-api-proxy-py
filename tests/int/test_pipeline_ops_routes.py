"""The non-inference surface, on the chain that actually serves requests.

Until 2026-08-19 the new chain answered 404 to `/health/readiness` while the existing chain answered it — and the existing chain is the one two of the three entry points still run. A supervisor pointed at the new chain had nothing to ask.
"""

from collections.abc import Mapping
from types import SimpleNamespace
from typing import Any

import httpx2
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY

from app.config.schema import ProxyConfig
from app.model_provider.types import ModelDescriptor, ModelEndpoint
from app.observability.metrics import RESPONSIVENESS
from app.server.app_state import CHAIN_STATE_KEY
from app.server.routes.ops import router as ops_router
from app.server.routes.router import build_router


class StubProvider:
    def __init__(
        self, name: str, ids: frozenset[str], *, disabled: frozenset[str] = frozenset()
    ) -> None:
        self.name = name
        self._ids = ids
        self._disabled = disabled

    @property
    def available_ids(self) -> frozenset[str]:
        return self._ids

    @property
    def raw_catalog(self) -> Mapping[str, Any]:
        return {}

    @property
    def disabled_ids(self) -> frozenset[str]:
        return self._disabled

    @property
    def base_url(self) -> str:
        return f"https://{self.name}.invalid"

    @property
    def catalog_refreshed_at(self) -> str:
        # Empty means never loaded, which is what an empty catalog stands for here.
        return "2026-08-27T00:00:00+00:00" if self._ids or self._disabled else ""

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
    def __init__(
        self,
        providers: dict[str, StubProvider],
        *,
        default: str | None = None,
        fallback: str = "",
    ) -> None:
        self._providers = providers
        self._default = default or next(iter(providers))
        self._fallback = fallback

    @property
    def names(self) -> frozenset[str]:
        return frozenset(self._providers)

    @property
    def default(self) -> StubProvider:
        return self._providers[self._default]

    @property
    def default_name(self) -> str:
        return self._default

    @property
    def fallback_name(self) -> str:
        return self._fallback

    def get(self, name: str) -> StubProvider:
        return self._providers[name]


def client_for(
    ids: frozenset[str],
    config: ProxyConfig | None = None,
    *,
    providers: dict[str, StubProvider] | None = None,
    default: str | None = None,
    fallback: str = "",
) -> httpx2.AsyncClient:
    app = FastAPI()
    app.include_router(ops_router)
    built = providers if providers is not None else {"ghc": StubProvider("ghc", ids)}
    registry = StubRegistry(built, default=default, fallback=fallback)
    # Only what the routes under test read; standing up a whole Chain would tie these to composition. A default `ProxyConfig()` rather than `None` since 2026-08-27: the model list and the status document both consult `model_mappings` now, because routing does.
    setattr(
        app.state,
        CHAIN_STATE_KEY,
        SimpleNamespace(providers=registry, config=config or ProxyConfig()),
    )
    return httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), base_url="http://t")


def config_with(mappings: dict[str, str], **rest: Any) -> ProxyConfig:
    return ProxyConfig.model_validate({"model_mappings": mappings, **rest})


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
    body = response.json()
    assert body["status"] == "ready"
    assert body["default_model_provider"] == "ghc"


@pytest.mark.asyncio
async def test_readiness_follows_the_default_provider_and_not_merely_some_provider() -> None:
    """Spec §4.3. With two providers `any(...)` reports ready off the wrong one.

    B is the default and has nothing; A is healthy. Every request that names no qualifier — nearly all of them — resolves against B and is refused, so answering 200 here would tell a supervisor to send traffic to a process that will reject it. This is the same argument the single-provider version of this endpoint already made about an empty catalog, one provider later.
    """
    providers = {
        "A": StubProvider("A", frozenset({"claude-opus-5"})),
        "B": StubProvider("B", frozenset()),
    }
    async with client_for(frozenset(), providers=providers, default="B") as client:
        response = await client.get("/health/readiness")
    assert response.status_code == 503


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/models", "/v1/models", "/openai/v1/models"])
async def test_the_model_list_is_the_catalog_routing_consults(path: str) -> None:
    """Listing anything routing would refuse would send a client after a model it cannot have."""
    async with client_for(frozenset({"claude-opus-5", "gpt-5.6-terra"})) as client:
        response = await client.get(path)
    assert response.status_code == 200
    assert [entry["id"] for entry in response.json()["data"]] == ["claude-opus-5", "gpt-5.6-terra"]


@pytest.mark.asyncio
async def test_the_model_list_names_the_provider_that_would_actually_answer() -> None:
    """Spec §4.1. `owned_by` used to be the default provider's name on every row — a constant.

    Here `claude-opus-4.8` is qualified to A while everything unqualified falls to B, so the two rows carry different owners. A list that reported one owner for both would be describing a proxy that does not exist.
    """
    providers = {
        "A": StubProvider("A", frozenset({"claude-opus-5"})),
        "B": StubProvider("B", frozenset({"gpt-5.6-terra"})),
    }
    config = config_with({"claude-opus-4.8": "A/claude-opus-5"})
    async with client_for(frozenset(), config, providers=providers, default="B") as client:
        response = await client.get("/v1/models")
    owners = {entry["id"]: entry["owned_by"] for entry in response.json()["data"]}
    assert owners["claude-opus-4.8"] == "A"
    assert owners["gpt-5.6-terra"] == "B"


@pytest.mark.asyncio
async def test_the_model_list_carries_the_aliases_a_client_could_send() -> None:
    """Spec §4.1. Catalog ids alone leave out the names most clients are configured to send.

    Worse than incomplete: with `claude-opus-4.8` routed to A and nothing else pointing there, an ids-only list would show A's model as B's and A's own route nowhere at all.
    """
    config = config_with({"opus": "claude-opus-5"})
    async with client_for(frozenset({"claude-opus-5"}), config) as client:
        response = await client.get("/v1/models")
    listed = {entry["id"] for entry in response.json()["data"]}
    assert {"opus", "claude-opus-5"} <= listed


@pytest.mark.asyncio
async def test_the_model_list_omits_what_the_chosen_provider_cannot_serve() -> None:
    """The other half of "routing-reachable": present in some catalog is not enough."""
    providers = {
        "A": StubProvider("A", frozenset({"claude-opus-5"})),
        "B": StubProvider("B", frozenset({"gpt-5.6-terra"})),
    }
    async with client_for(frozenset(), providers=providers, default="B") as client:
        response = await client.get("/v1/models")
    listed = {entry["id"] for entry in response.json()["data"]}
    # A offers it, but nothing routes there, so a client sending it would reach B and be refused.
    assert "claude-opus-5" not in listed
    assert "gpt-5.6-terra" in listed


@pytest.mark.asyncio
async def test_metrics_are_served() -> None:
    before = REGISTRY.get_sample_value("ghc_proxy_event_loop_monitor_active")
    assert before is not None
    RESPONSIVENESS.loop_active.inc(7)
    try:
        async with client_for(frozenset({"m"})) as client:
            response = await client.get("/metrics")
    finally:
        RESPONSIVENESS.loop_active.dec(7)

    assert response.status_code == 200
    assert b"python_gc_objects_collected_total" in response.content
    assert b"ghc_proxy_event_loop_lag_seconds_count" in response.content
    assert b"ghc_proxy_event_loop_lag_max_seconds" in response.content
    assert b"ghc_proxy_event_loop_lag_failures_total" in response.content
    assert b"ghc_proxy_tui_last_render_age_seconds" in response.content
    assert b"ghc_proxy_tui_terminal_io_in_progress_seconds" in response.content
    assert f"ghc_proxy_event_loop_monitor_active {before + 7}".encode() in response.content


@pytest.mark.asyncio
async def test_api_status_and_readiness_cannot_disagree_about_readiness() -> None:
    """They are two documents now, but one judgement.

    `/api/status` grew a route table and stopped being an alias for the health check — `api.md` files it under status rather than health, and once two providers can be configured there is a great deal to report that readiness has no opinion about. What must not follow is a second derivation of readiness itself: that is exactly the drift the shared handler existed to prevent, and splitting the handlers does not license splitting the judgement.

    Both catalog states are exercised, because a `ready` field hard-coded to either value would pass a single-state test.
    """
    for ids in (frozenset[str](), frozenset({"claude-opus-5"})):
        async with client_for(ids) as client:
            health = await client.get("/health/readiness")
            status = await client.get("/api/status")
        # Always readable: a status document that refuses to answer when the news is bad is useless.
        assert status.status_code == 200
        assert status.json()["ready"] is (health.status_code == 200)


@pytest.mark.asyncio
async def test_api_status_reports_where_every_name_would_go_and_why() -> None:
    """Spec §4.2. The `origin` of each row is what tells a deliberate route from an accident."""
    providers = {
        "A": StubProvider("A", frozenset({"claude-opus-5"})),
        "B": StubProvider("B", frozenset({"gpt-5.6-terra"})),
    }
    config = config_with({"claude-opus-4.8": "A/claude-opus-5", "gpt": "gpt-5.6-terra"})
    async with client_for(frozenset(), config, providers=providers, default="B") as client:
        body = (await client.get("/api/status")).json()

    assert body["default_model_provider"] == "B"
    routes = body["routes"]
    assert routes["claude-opus-4.8"] == {
        "provider": "A",
        "model": "claude-opus-5",
        "origin": "qualified",
        "serviceable": "yes",
    }
    # No qualifier anywhere on its chain, so it lands on the default — the state §6.1 calls out as the silent one, and the reason the table carries every name rather than only configured ones.
    assert routes["gpt"]["origin"] == "default"
    assert routes["gpt"]["provider"] == "B"


@pytest.mark.asyncio
async def test_api_status_tells_a_disabled_model_from_a_missing_one() -> None:
    """Spec §4.2.2. `available_ids` merges them and `describe()` merges them; an operator must not.

    The fix for one is to wait on upstream and the fix for the other is to edit a list, so a single `false` — which is what this field was in the first draft — sends half the readers to the wrong place.
    """
    providers = {
        "A": StubProvider("A", frozenset(), disabled=frozenset({"gpt-5.6-terra"})),
    }
    config = config_with({"x": "A/gpt-5.6-terra", "y": "A/never-existed"})
    async with client_for(frozenset(), config, providers=providers, default="A") as client:
        routes = (await client.get("/api/status")).json()["routes"]
    assert routes["x"]["serviceable"] == "disabled"
    assert routes["y"]["serviceable"] == "absent"


@pytest.mark.asyncio
async def test_api_status_says_unroutable_rather_than_inventing_a_provider() -> None:
    """Spec §4.2.2. A qualifier naming nothing, with no fallback configured, has no provider at all.

    The row still has to exist — it is the one an operator opened this to find — and its `provider` is `null`, because the alternatives are to omit the row or to name a provider that will never serve it.
    """
    config = config_with({"x": "typo/claude-opus-5"})
    async with client_for(frozenset({"claude-opus-5"}), config) as client:
        body = (await client.get("/api/status")).json()
    assert body["fallback_model_provider"] is None
    assert body["routes"]["x"] == {
        "provider": None,
        "model": "claude-opus-5",
        "origin": "fallback",
        "serviceable": "unroutable",
    }


@pytest.mark.asyncio
async def test_api_status_reports_an_unloaded_catalog_as_unknown_not_missing() -> None:
    """Spec §4.2.2. With nothing loaded, "this model is not there" is not a thing anyone can say."""
    async with client_for(frozenset(), config_with({"x": "claude-opus-5"})) as client:
        body = (await client.get("/api/status")).json()
    assert body["providers"]["ghc"]["catalog"] == "empty"
    assert body["providers"]["ghc"]["catalog_refreshed_at"] is None
    assert body["routes"]["x"]["serviceable"] == "unknown"


@pytest.mark.asyncio
async def test_api_status_counts_available_and_disabled_separately() -> None:
    """Spec §4.2.3: they sum to the catalog, so neither alone answers "how big is it"."""
    providers = {"A": StubProvider("A", frozenset({"a", "b"}), disabled=frozenset({"c"}))}
    async with client_for(frozenset(), providers=providers) as client:
        entry = (await client.get("/api/status")).json()["providers"]["A"]
    assert entry["models"] == 2
    assert entry["disabled"] == 1
    assert entry["base_url"] == "https://A.invalid"


@pytest.mark.asyncio
async def test_a_disabled_model_is_recognised_through_an_equivalent_spelling() -> None:
    """Every other model-name comparison in this code folds case and `.`/`-`; this one used not to.

    An operator copying an id out of a 41-line `disabled_models` block may well write `gpt-5-6-terra` for `gpt-5.6-terra`. Under an exact match the row came back `absent` — "not in A's catalogue" — about a model that is sitting in A's catalogue, which is the precise sentence the `disabled` value exists to stop being said.
    """
    providers = {"A": StubProvider("A", frozenset(), disabled=frozenset({"gpt-5.6-terra"}))}
    config = config_with({"x": "A/gpt-5-6-terra", "y": "A/GPT-5.6-Terra"})
    async with client_for(frozenset(), config, providers=providers, default="A") as client:
        routes = (await client.get("/api/status")).json()["routes"]
    assert routes["x"]["serviceable"] == "disabled"
    assert routes["y"]["serviceable"] == "disabled"


@pytest.mark.asyncio
async def test_a_candidate_with_a_format_suffix_resolves_the_way_a_request_would() -> None:
    """The table and the wire must not answer differently about one name.

    `decide_route` strips `@format` before anything is looked up, so a mapping key carrying one is never matched — a request for `x@anthropic-messages` resolves `x`. A table that skipped that step listed the key as a servable id while the real request went to the default and was refused.
    """
    providers = {"A": StubProvider("A", frozenset({"claude-opus-5"}))}
    config = config_with({"x@anthropic-messages": "A/claude-opus-5"})
    async with client_for(frozenset(), config, providers=providers, default="A") as client:
        listed = {entry["id"] for entry in (await client.get("/v1/models")).json()["data"]}
    assert "x@anthropic-messages" not in listed


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


@pytest.mark.asyncio
async def test_api_config_redacts_only_xingchen_credentials() -> None:
    config = ProxyConfig.model_validate(
        {
            "model_providers": {
                "xingchen": {
                    "type": "xingchen",
                    "models": ["chat-pro"],
                    "gateway_api_key": "gateway-secret",
                    "x_token": "complete.secret.token",
                    "device_id": "device-id",
                    "install_id": "install-id",
                }
            },
            "default_model_provider": "xingchen",
        }
    )
    async with client_for(frozenset({"m"}), config) as client:
        response = await client.get("/api/config")

    assert response.status_code == 200
    serialized = response.text
    provider = response.json()["model_providers"]["xingchen"]
    assert "gateway-secret" not in serialized
    assert "complete.secret.token" not in serialized
    assert provider["gateway_api_key"] == "***"
    assert provider["x_token"] == "***"
    assert provider["models"] == ["chat-pro"]
    assert provider["device_id"] == "device-id"
    assert provider["install_id"] == "install-id"
    assert provider["api_base_url"] == "https://agent.teleai.com.cn/superCowork/sapi/api/v1"


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
