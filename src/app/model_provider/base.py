"""The contract a model provider satisfies.

A provider owns one upstream's catalog and its endpoints.
It answers what a model can do and sends requests.
It does not translate formats, resolve aliases, orchestrate retries or decide routing.
"""

from collections.abc import Mapping
from typing import Any, Protocol

import httpx2

from app.model_provider.types import ModelDescriptor, ModelEndpoint


class ModelProvider(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def available_ids(self) -> frozenset[str]: ...

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
        model_id: str,
        stream: bool = False,
        extra_headers: Mapping[str, str] | None = None,
    ) -> httpx2.Response:
        """Send one request to one endpoint.

        Raises before touching the network when the model does not advertise the endpoint.
        """
        ...

    async def count_tokens(
        self,
        payload: Mapping[str, Any],
        *,
        model_id: str,
    ) -> httpx2.Response:
        """Ask upstream how many tokens an Anthropic Messages body comes to.

        On the protocol rather than on one implementation because the spec's
        `inbound.anthropic_count_tokens.providers` names `ghc` as one provider among others; a
        counter that only some providers offered could not be selected by name.

        Gated on the Messages capability, the same as sending that body would be.
        """
        ...
