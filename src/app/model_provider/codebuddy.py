"""CodeBuddy (Tencent `copilot.tencent.com`) as a model provider.

Structured to mirror `github_copilot.py`: the same protocol, the same descriptor
vocabulary, the same report surfaces — the routing layer, `/api/status` and the
debug tooling cannot tell the two providers apart, which is what makes a second
upstream a configuration fact rather than a code path.

The upstream speaks one endpoint. Its only inference path is
`/v2/chat/completions`, so every descriptor advertises exactly that and requests
wanting `/v1/messages` or `/responses` from this provider are translated onto it
by the pipeline's translation registry.
"""

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

import httpx2

from app.config.schema import CodebuddyProviderConfig
from app.model_provider.codebuddy_client import CodebuddyClient, static_catalog
from app.model_provider.types import (
    CatalogSnapshot,
    EndpointNotImplemented,
    ModelDescriptor,
    ModelEndpoint,
    UnknownModel,
    parse_prompt_token_limits,
    require_endpoint,
    resolve_endpoints,
)

PROVIDER_TYPE = "codebuddy"

# Chat Completions is the one wire this upstream speaks. `ws:/responses` and the
# rest are absent because the upstream has no such path to advertise.
_SEND_METHODS = {
    ModelEndpoint.OPENAI_CHAT_COMPLETIONS: "send_chat_completions",
}

# Which advertised endpoints this proxy can actually drive. Same contract as
# `github_copilot.DRIVEN_ENDPOINTS`: derived from the send table so a report of
# what is drivable cannot drift from what `send` will take.
DRIVEN_ENDPOINTS: frozenset[ModelEndpoint] = frozenset(_SEND_METHODS)


class CodebuddyProvider:
    def __init__(
        self,
        name: str,
        client: CodebuddyClient,
        config: CodebuddyProviderConfig,
        *,
        base_url: str,
    ) -> None:
        self._name = name
        self._client = client
        self._config = config
        self._base_url = base_url
        self._disabled = frozenset(config.disabled_models)
        self._descriptors: dict[str, ModelDescriptor] = {}
        self._raw_catalog: dict[str, Any] = {"object": "list", "data": []}
        self._refreshed_at: str = ""
        self._catalog_generation = 0
        self.replace_catalog(static_catalog())

    @property
    def name(self) -> str:
        return self._name

    @property
    def base_url(self) -> str:
        """Where this provider's inference calls go. Reported, never reconstructed from config by a caller."""
        return self._base_url

    @property
    def catalog_refreshed_at(self) -> str:
        """When the descriptors below were last replaced. `""` until that has happened once."""
        return self._refreshed_at

    @property
    def raw_catalog(self) -> Mapping[str, Any]:
        """The catalog exactly as this provider publishes it.

        Static rather than fetched — the backend advertises no `/models` endpoint —
        so "raw" means the table this deployment serves, in the same wire shape a
        Copilot catalog takes.
        """
        return self._raw_catalog

    @property
    def catalog_snapshot(self) -> CatalogSnapshot:
        return CatalogSnapshot(
            raw=self._raw_catalog,
            # Static: the backend advertises no `/models` endpoint, so the table is
            # what this provider serves rather than something a fetch returned.
            source="static",
            driven_endpoints=DRIVEN_ENDPOINTS,
        )

    @property
    def available_ids(self) -> frozenset[str]:
        return frozenset(self._descriptors) - self._disabled

    @property
    def disabled_ids(self) -> frozenset[str]:
        # Intersected with the catalog: a `disabled_models` entry for a model this
        # upstream never offered is a stale config line, not a disabled model, and
        # counting it would break `models + disabled == catalog size`.
        return frozenset(self._descriptors) & self._disabled

    def describe(self, model_id: str) -> ModelDescriptor | None:
        if model_id in self._disabled:
            return None
        return self._descriptors.get(model_id)

    def replace_catalog(self, raw: Mapping[str, Any]) -> None:
        """Rebuild the descriptors from a catalog in the Copilot wire shape.

        The parse is the GitHub Copilot provider's, unchanged on purpose: one
        catalog grammar, one parser, so a report reads both providers the same way.
        """
        entries = raw.get("data")
        if not isinstance(entries, list):
            raise ValueError("models response data must be a list")
        generation = self._catalog_generation + 1
        refreshed_at = datetime.now(UTC).isoformat(timespec="seconds")
        descriptors: dict[str, ModelDescriptor] = {}
        for entry in entries:  # pyright: ignore[reportUnknownVariableType]
            if not isinstance(entry, dict):
                continue
            model = dict[str, Any](entry)  # pyright: ignore[reportUnknownArgumentType]
            model_id = model.get("id")
            if not isinstance(model_id, str) or not model_id:
                continue
            resolved = resolve_endpoints(
                model.get("supported_endpoints"),
                model_type="chat",
            )
            descriptors[model_id] = ModelDescriptor(
                id=model_id,
                endpoints=resolved.known,
                unknown_endpoints=resolved.unknown,
                provider_name=self._name,
                catalog_generation=generation,
                catalog_refreshed_at=refreshed_at,
                prompt_token_limits=parse_prompt_token_limits(model),
            )
        self._descriptors = descriptors
        self._raw_catalog = dict(raw)
        self._catalog_generation = generation
        # Stamped only here, so it marks a successful replacement rather than an
        # attempt — the same rule the Copilot provider applies.
        self._refreshed_at = refreshed_at

    async def refresh_catalog(self) -> bool:
        """Re-read the static table. Returns whether it changed — it cannot.

        The catalog has no upstream to refetch, so a refresh re-serves the same
        table. Kept on the protocol rather than answered from a flag so
        `refresh_catalogs` and the debug tooling can walk every provider
        uniformly; the timestamp is stamped by construction, not by this call.
        """
        return False

    async def send(
        self,
        endpoint: ModelEndpoint,
        payload: Mapping[str, Any],
        *,
        model_id: str,
        stream: bool = False,
        extra_headers: Mapping[str, str] | None = None,
    ) -> httpx2.Response:
        descriptor = self.describe(model_id)
        if descriptor is None:
            raise UnknownModel(self._name, model_id)
        require_endpoint(descriptor, endpoint, self._name)
        if endpoint not in _SEND_METHODS:
            raise EndpointNotImplemented(self._name, endpoint.value)
        return await self._client.send_chat_completions(payload, stream=stream)

    async def count_tokens(
        self,
        payload: Mapping[str, Any],
        *,
        model_id: str,
    ) -> httpx2.Response:
        """Anthropic token counting.

        Gated on the Messages capability like every provider. No model here
        advertises `/v1/messages`, so the gate refuses before any network call and
        the configured counting chain falls through to its next leg.
        """
        descriptor = self.describe(model_id)
        if descriptor is None:
            raise UnknownModel(self._name, model_id)
        require_endpoint(descriptor, ModelEndpoint.ANTHROPIC_MESSAGES, self._name)
        raise EndpointNotImplemented(self._name, ModelEndpoint.ANTHROPIC_MESSAGES.value)
