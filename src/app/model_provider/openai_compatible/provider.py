"""The sub2api provider, which natively serves three protocol endpoints."""

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, cast

import httpx2

from app.config.schema import OpenAICompatibleProviderConfig
from app.model_provider.openai_compatible.client import OpenAICompatibleClient
from app.model_provider.types import (
    CatalogSnapshot,
    CatalogSource,
    ChatEndpointCapabilities,
    ChatResponseMode,
    EndpointNotImplemented,
    ModelDescriptor,
    ModelEndpoint,
    parse_prompt_token_limits,
    require_descriptor_owner,
    require_endpoint,
    resolve_endpoints,
)

PROVIDER_TYPE = "sub2api"
PROVIDER_TYPES = frozenset({PROVIDER_TYPE})

_SEND_METHODS = {
    ModelEndpoint.ANTHROPIC_MESSAGES,
    ModelEndpoint.OPENAI_RESPONSES,
    ModelEndpoint.OPENAI_CHAT_COMPLETIONS,
    ModelEndpoint.OPENAI_EMBEDDINGS,
}
DRIVEN_ENDPOINTS = frozenset(_SEND_METHODS)
_DEFAULT_ENDPOINTS = frozenset(
    {
        ModelEndpoint.ANTHROPIC_MESSAGES,
        ModelEndpoint.OPENAI_RESPONSES,
        ModelEndpoint.OPENAI_CHAT_COMPLETIONS,
    }
)

_CHAT_ENDPOINT_CAPABILITIES = ChatEndpointCapabilities(
    response_modes=frozenset(
        {ChatResponseMode.STREAMING, ChatResponseMode.NON_STREAMING}
    ),
    stream_options_include_usage_default=None,
    tool_stream_default=None,
    provenance="OpenAI-compatible provider catalog",
)


def _normalise_endpoints(value: object) -> object:
    if not isinstance(value, list):
        return value
    entries = cast(list[Any], value)
    aliases = {
        "/v1/responses": ModelEndpoint.OPENAI_RESPONSES.value,
        "/v1/chat/completions": ModelEndpoint.OPENAI_CHAT_COMPLETIONS.value,
        "/v1/embeddings": ModelEndpoint.OPENAI_EMBEDDINGS.value,
    }
    return [
        aliases.get(entry, entry) if isinstance(entry, str) else entry
        for entry in entries
    ]


class OpenAICompatibleProvider:
    def __init__(
        self,
        name: str,
        client: OpenAICompatibleClient,
        config: OpenAICompatibleProviderConfig,
    ) -> None:
        self._name = name
        self._client = client
        self._config = config
        self._disabled = frozenset(config.disabled_models)
        self._catalog_generation = 0
        self._refreshed_at = ""
        self._raw_catalog: dict[str, Any] = {"object": "list", "data": []}
        self._catalog_source: CatalogSource = "upstream"
        self._descriptors: dict[str, ModelDescriptor] = {}

    @property
    def name(self) -> str:
        return self._name

    @property
    def base_url(self) -> str:
        return self._client.base_url

    @property
    def catalog_refreshed_at(self) -> str:
        return self._refreshed_at

    @property
    def raw_catalog(self) -> Mapping[str, Any]:
        return self._raw_catalog

    @property
    def catalog_snapshot(self) -> CatalogSnapshot:
        return CatalogSnapshot(
            raw=self._raw_catalog,
            source=self._catalog_source,
            driven_endpoints=DRIVEN_ENDPOINTS,
        )

    @property
    def available_ids(self) -> frozenset[str]:
        return frozenset(self._descriptors) - self._disabled

    @property
    def disabled_ids(self) -> frozenset[str]:
        return frozenset(self._descriptors) & self._disabled

    def describe(self, model_id: str) -> ModelDescriptor | None:
        if model_id in self._disabled:
            return None
        return self._descriptors.get(model_id)

    def replace_catalog(
        self,
        raw: Mapping[str, Any],
        *,
        source: CatalogSource = "upstream",
    ) -> None:
        entries = raw.get("data")
        if not isinstance(entries, list):
            raise ValueError("models response data must be a list")
        generation = self._catalog_generation + 1
        refreshed_at = datetime.now(UTC).isoformat(timespec="seconds")
        allowed_models = frozenset(self._config.models)
        descriptors: dict[str, ModelDescriptor] = {}
        for entry in cast(list[Any], entries):
            if not isinstance(entry, dict):
                continue
            model = cast(dict[str, Any], entry)
            model_id = model.get("id")
            if not isinstance(model_id, str) or not model_id:
                continue
            if allowed_models and model_id not in allowed_models:
                continue
            advertised = _normalise_endpoints(model.get("supported_endpoints"))
            resolved = (
                None
                if advertised is None
                else resolve_endpoints(advertised, model_type="chat")
            )
            endpoints = _DEFAULT_ENDPOINTS if resolved is None else resolved.known
            descriptors[model_id] = ModelDescriptor(
                id=model_id,
                endpoints=endpoints,
                unknown_endpoints=() if resolved is None else resolved.unknown,
                chat_endpoint_capabilities=(
                    _CHAT_ENDPOINT_CAPABILITIES
                    if ModelEndpoint.OPENAI_CHAT_COMPLETIONS in endpoints
                    else None
                ),
                provider_name=self._name,
                catalog_generation=generation,
                catalog_refreshed_at=refreshed_at,
                prompt_token_limits=parse_prompt_token_limits(model),
            )
        self._descriptors = descriptors
        self._raw_catalog = dict(raw)
        self._catalog_source = source
        self._catalog_generation = generation
        self._refreshed_at = refreshed_at

    async def refresh_catalog(self) -> bool:
        raw = await self._client.fetch_models()
        before = self._raw_catalog
        self.replace_catalog(raw)
        return raw != before

    async def send(
        self,
        endpoint: ModelEndpoint,
        payload: Mapping[str, Any],
        *,
        descriptor: ModelDescriptor,
        stream: bool = False,
        extra_headers: Mapping[str, str] | None = None,
        interaction_id: str | None = None,
    ) -> httpx2.Response:
        del interaction_id
        require_descriptor_owner(descriptor, self._name)
        require_endpoint(descriptor, endpoint, self._name)
        if endpoint not in _SEND_METHODS:
            raise EndpointNotImplemented(self._name, endpoint.value)
        return await self._client.send(
            endpoint,
            payload,
            stream=stream,
            extra_headers=extra_headers,
        )

    async def count_tokens(
        self,
        payload: Mapping[str, Any],
        *,
        descriptor: ModelDescriptor,
    ) -> httpx2.Response:
        require_descriptor_owner(descriptor, self._name)
        require_endpoint(descriptor, ModelEndpoint.ANTHROPIC_MESSAGES, self._name)
        return await self._client.count_tokens(payload)
