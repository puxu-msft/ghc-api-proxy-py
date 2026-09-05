"""The contract a model provider satisfies.

A provider owns one upstream's catalog and its endpoints.
It answers what a model can do and sends requests.
It does not translate formats, resolve aliases, orchestrate retries or decide routing.
"""

from collections.abc import Mapping
from typing import Any, Protocol, runtime_checkable

import httpx2

from app.model_provider.types import CatalogSnapshot, ModelDescriptor, ModelEndpoint


@runtime_checkable
class CatalogProvider(Protocol):
    """Optional diagnostics seam for providers that can expose a complete catalog snapshot."""

    @property
    def catalog_snapshot(self) -> CatalogSnapshot: ...


class ModelProvider(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def base_url(self) -> str:
        """Where this provider's requests actually go, after any per-account resolution.

        On the protocol because `/api/status` reports it, and reporting it from configuration instead would print what was *asked for* — while `resolve_provider_base_urls` may have derived something else from the account's subscription. Those differ exactly when an operator most wants to look.
        """
        ...

    @property
    def catalog_refreshed_at(self) -> str:
        """ISO timestamp of the last **successful** catalog load, or `""` if there has not been one.

        Empty rather than a sentinel date: "never" is a state an operator acts on, and any date chosen to mean it would eventually be mistaken for a real one.
        """
        ...

    @property
    def available_ids(self) -> frozenset[str]: ...

    @property
    def raw_catalog(self) -> Mapping[str, Any]:
        """The catalog exactly as upstream published it, for reporting.

        On the protocol rather than on one implementation because the debug tooling
        renders any provider's catalog, and a property only some providers had made
        that tooling branch on types to ask a question every provider can answer.
        Static catalogs count: what a provider serves is what upstream said, even
        when upstream said it to the reference implementation instead of over HTTP.
        """
        ...

    @property
    def disabled_ids(self) -> frozenset[str]:
        """Ids the catalog advertises that this deployment switched off.

        Exists so a report can tell "upstream has no such model" from "you turned it off" — two states `describe()` deliberately merges into `None`, because routing must refuse both, and two states an operator must **not** have merged, because the fix for one is to wait on upstream and the fix for the other is to edit a list. Spec §4.2.2.

        Intersected with the catalog, not the raw configured list: a `disabled_models` entry naming a model this upstream never offered is not a disabled model, it is a stale line in the config, and counting it would make the arithmetic in `/api/status` (`models + disabled` = catalog size) stop holding.
        """
        ...

    def describe(self, model_id: str) -> ModelDescriptor | None:
        """Return what is known about a model, or `None` when it is not on offer.

        A disabled model is not on offer, so callers cannot route to it by accident.
        """
        ...

    async def refresh_catalog(self) -> bool:
        """Refetch the catalog. Returns whether it changed."""
        ...

    async def send(
        self,
        endpoint: ModelEndpoint,
        payload: Mapping[str, Any],
        *,
        descriptor: ModelDescriptor,
        stream: bool = False,
        extra_headers: Mapping[str, str] | None = None,
    ) -> httpx2.Response:
        """Send one request to one endpoint.

        The descriptor is the immutable snapshot routing selected. Raises before touching the network when another provider issued it or the model does not advertise the endpoint.
        """
        ...

    async def count_tokens(
        self,
        payload: Mapping[str, Any],
        *,
        descriptor: ModelDescriptor,
    ) -> httpx2.Response:
        """Ask upstream how many tokens an Anthropic Messages body comes to.

        On the protocol rather than on one implementation because the spec's `inbound.anthropic_count_tokens.providers` names a model provider among the legs it may try; a counter that only some providers offered could not be selected by name.

        Gated on descriptor ownership and the Messages capability, the same as sending that body would be.
        """
        ...
