"""GitHub Copilot as a model provider, backed by the `app.ghc_client` library."""

from collections.abc import Mapping
from typing import Any, cast

import httpx2

from app.config.schema import ModelProviderConfig
from app.ghc_client import GhcApiClient, fetch_models
from app.model_provider.types import (
    EndpointNotImplemented,
    ModelDescriptor,
    ModelEndpoint,
    UnknownModel,
    model_type_of,
    require_endpoint,
    resolve_endpoints,
)

PROVIDER_TYPE = "github_copilot"


def _string_mapping(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    entries = cast(dict[object, object], value)
    return {str(key): str(item) for key, item in entries.items()}


# ws:/responses is deliberately absent: the spec lists it as unsupported.
_SEND_METHODS = {
    ModelEndpoint.ANTHROPIC_MESSAGES: "send_anthropic_messages",
    ModelEndpoint.OPENAI_CHAT_COMPLETIONS: "send_chat_completions",
    ModelEndpoint.OPENAI_RESPONSES: "send_responses",
    ModelEndpoint.OPENAI_EMBEDDINGS: "send_embeddings",
}

# Which advertised endpoints this proxy can actually drive. Derived from the send table rather than written out again, so a report of what is drivable cannot drift from what `send` will take.
DRIVEN_ENDPOINTS: frozenset[ModelEndpoint] = frozenset(_SEND_METHODS)


class GithubCopilotProvider:
    def __init__(
        self,
        name: str,
        client: GhcApiClient,
        config: ModelProviderConfig,
        *,
        http_client: httpx2.AsyncClient,
        base_url: str,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        self._name = name
        self._client = client
        self._config = config
        self._http = http_client
        self._base_url = base_url
        self._catalog_headers = dict(headers or {})
        self._disabled = frozenset(config.disabled_models)
        self._descriptors: dict[str, ModelDescriptor] = {}
        self._raw_catalog: dict[str, Any] = {"object": "list", "data": []}
        self._etag: str | None = None

    @property
    def name(self) -> str:
        return self._name

    @property
    def base_url(self) -> str:
        """Where this provider's inference and catalog calls go. Reported, never reconstructed from config by a caller."""
        return self._base_url

    @property
    def raw_catalog(self) -> Mapping[str, Any]:
        """The catalog exactly as upstream sent it.

        Kept beside the descriptors rather than derived back from them: the descriptors are a projection built for routing and drop nearly everything else the catalog said, so anything reporting on the catalog itself would otherwise have to fetch it a second time.
        """
        return self._raw_catalog

    @property
    def available_ids(self) -> frozenset[str]:
        return frozenset(self._descriptors) - self._disabled

    def describe(self, model_id: str) -> ModelDescriptor | None:
        if model_id in self._disabled:
            return None
        return self._descriptors.get(model_id)

    def replace_catalog(self, raw: Mapping[str, Any]) -> None:
        entries = raw.get("data")
        if not isinstance(entries, list):
            raise ValueError("models response data must be a list")
        descriptors: dict[str, ModelDescriptor] = {}
        for entry in entries:  # pyright: ignore[reportUnknownVariableType]
            if not isinstance(entry, dict):
                continue
            model = dict[str, Any](entry)  # pyright: ignore[reportUnknownArgumentType]
            model_id = model.get("id")
            if not isinstance(model_id, str) or not model_id:
                continue
            # `resolve_endpoints` rather than `parse_endpoints`: Copilot omits `supported_endpoints` for part of its catalog, and those models are served on the standard endpoint for their kind rather than being endpoint-less. Reading that here, once, is what keeps routing and any report of the catalog from answering the question differently.
            resolved = resolve_endpoints(
                model.get("supported_endpoints"),
                model_type=model_type_of(model),
            )
            descriptors[model_id] = ModelDescriptor(
                id=model_id,
                endpoints=resolved.known,
                unknown_endpoints=resolved.unknown,
                request_headers=_string_mapping(model.get("request_headers")),
            )
        self._descriptors = descriptors
        self._raw_catalog = dict(raw)

    async def refresh_catalog(self) -> bool:
        """Refetch the catalog, authenticating as of now.

        The headers are obtained per call rather than held from construction: the Copilot token
        expires, so a set captured once would authenticate the first refresh and nothing after it.
        Held headers are merged on top for the catalog-specific extras a caller passed in.
        """
        headers = await self._client.request_headers(extra_headers=self._catalog_headers)
        page = await fetch_models(
            self._http,
            self._base_url,
            headers,
            etag=self._etag,
        )
        if page is None:
            return False
        self.replace_catalog(page.raw)
        if page.etag:
            self._etag = page.etag
        return True

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

        if endpoint is ModelEndpoint.ANTHROPIC_MESSAGES:
            return await self._client.send_anthropic_messages(
                payload,
                stream=stream,
                extra_headers=extra_headers,
            )
        if endpoint is ModelEndpoint.OPENAI_CHAT_COMPLETIONS:
            return await self._client.send_chat_completions(
                payload,
                stream=stream,
                extra_headers=extra_headers,
            )
        if endpoint is ModelEndpoint.OPENAI_RESPONSES:
            return await self._client.send_responses(
                payload,
                stream=stream,
                extra_headers=extra_headers,
            )
        return await self._client.send_embeddings(payload)

    async def count_tokens(
        self,
        payload: Mapping[str, Any],
        *,
        model_id: str,
    ) -> httpx2.Response:
        """Anthropic token counting.

        The spec groups it with the Messages driver rather than giving it its own routing row.
        It is therefore gated on the Messages capability.
        """
        descriptor = self.describe(model_id)
        if descriptor is None:
            raise UnknownModel(self._name, model_id)
        require_endpoint(descriptor, ModelEndpoint.ANTHROPIC_MESSAGES, self._name)
        return await self._client.send_anthropic_count_tokens(payload)
