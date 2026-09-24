"""The bridge provider, which natively serves three protocol endpoints."""

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, cast

import httpx2

from app.config.schema import OpenAICompatibleProviderConfig
from app.model_provider.model_info import load_model_info, merge_model_info
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
    parse_reasoning_efforts,
    require_descriptor_owner,
    require_endpoint,
    resolve_endpoints,
)

PROVIDER_TYPE = "bridge"
PROVIDER_TYPES = frozenset({PROVIDER_TYPE})

_SEND_METHODS = {
    ModelEndpoint.ANTHROPIC_MESSAGES,
    ModelEndpoint.OPENAI_RESPONSES,
    ModelEndpoint.OPENAI_CHAT_COMPLETIONS,
    ModelEndpoint.OPENAI_EMBEDDINGS,
}
DRIVEN_ENDPOINTS = frozenset(_SEND_METHODS)
# The three protocols a bridge operator may declare as directly served. Their
# capability comes from config, so the constant that used to default them all on
# is gone: an undeclared protocol is disabled until an operator enables it.
_CONFIGURED_ENDPOINT_FIELDS = {
    ModelEndpoint.OPENAI_CHAT_COMPLETIONS: "openai_chat_completions_endpoint",
    ModelEndpoint.OPENAI_RESPONSES: "openai_responses_endpoint",
    ModelEndpoint.ANTHROPIC_MESSAGES: "anthropic_messages_endpoint",
}

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
        # Read once, at construction: this file is a restart-required setting like the
        # addresses beside it, and a path that cannot be read must fail the start-up
        # rather than quietly leave every model description as empty as upstream's.
        self._model_info = (
            load_model_info(config.model_info_json) if config.model_info_json.strip() else None
        )
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
    def model_info_freshness(self) -> dict[str, Any] | None:
        """Where the local model-info document came from, and how old its sample is.

        Optional because only a bridge can be configured with one, and `/api/status`
        reports it where it exists rather than forcing every provider to answer.
        """
        return None if self._model_info is None else self._model_info.freshness()

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

    def _enabled_direct_endpoints(self) -> frozenset[ModelEndpoint]:
        """The three chat protocols this upstream is configured to serve directly.

        Empty or `False` disables a protocol; `True` or a URL string enables it.
        The config and the client share this gate so capability and address agree.
        """
        return frozenset(
            endpoint
            for endpoint, field in _CONFIGURED_ENDPOINT_FIELDS.items()
            if getattr(self._config, field)
        )

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
        enabled_endpoints = self._enabled_direct_endpoints()
        described = None if self._model_info is None else self._model_info.models
        served: list[dict[str, Any]] = []
        descriptors: dict[str, ModelDescriptor] = {}
        for entry in cast(list[Any], entries):
            if not isinstance(entry, dict):
                continue
            model = cast(dict[str, Any], entry)
            model_id = model.get("id")
            if not isinstance(model_id, str) or not model_id:
                continue
            local = None if described is None else described.get(model_id)
            if described is not None and local is None:
                # The intersection is the point, and neither side answers it alone:
                # upstream advertises models this file says nothing about, and the file
                # names models upstream does not serve. What is left is what the
                # operator has both confirmed and described.
                continue
            if allowed_models and model_id not in allowed_models:
                # Before the merge, not after: `served` is what `/models` reads, and a
                # model the allowlist just dropped must not reappear there merely
                # because the local file happens to describe it.
                continue
            if local is not None:
                model = merge_model_info(model, local)
                served.append(model)
            advertised = _normalise_endpoints(model.get("supported_endpoints"))
            resolved = (
                None
                if advertised is None
                else resolve_endpoints(advertised, model_type="chat")
            )
            if resolved is None:
                # No advertised capability: fall back to exactly what the operator
                # declared as directly served (the old default-enabled-all-three).
                endpoints = enabled_endpoints
            else:
                # The catalogue is the upstream's claim; config is what this proxy
                # trusts it can reach directly. Keep the intersection for the
                # gated chat protocols, and keep embeddings (never gated) as-is.
                endpoints = frozenset(
                    endpoint
                    for endpoint in resolved.known
                    if endpoint in enabled_endpoints
                    or endpoint is ModelEndpoint.OPENAI_EMBEDDINGS
                )
            reasoning_efforts = parse_reasoning_efforts(model)
            if reasoning_efforts is None:
                reasoning_efforts = self._config.reasoning_efforts.get(model_id)
            descriptors[model_id] = ModelDescriptor(
                id=model_id,
                endpoints=endpoints,
                unknown_endpoints=() if resolved is None else resolved.unknown,
                chat_endpoint_capabilities=(
                    _CHAT_ENDPOINT_CAPABILITIES
                    if ModelEndpoint.OPENAI_CHAT_COMPLETIONS in endpoints
                    else None
                ),
                reasoning_efforts=reasoning_efforts,
                provider_name=self._name,
                catalog_generation=generation,
                catalog_refreshed_at=refreshed_at,
                prompt_token_limits=parse_prompt_token_limits(model),
            )
        self._descriptors = descriptors
        if described is None:
            self._raw_catalog = dict(raw)
        else:
            # `/models` reads its metadata straight out of the raw catalog, so the
            # merged entries have to land here or the intersection would only decide
            # which ids route while every description stayed as empty as upstream's.
            catalog = dict(raw)
            catalog["data"] = served
            self._raw_catalog = catalog
        self._catalog_source = source
        self._catalog_generation = generation
        self._refreshed_at = refreshed_at

    async def refresh_catalog(self) -> bool:
        raw = await self._client.fetch_models()
        before = self._raw_catalog
        self.replace_catalog(raw)
        # Compared after the merge, in both modes: the question is whether what this
        # provider serves changed. Against the upstream payload it would answer "yes"
        # on every refresh whenever a local file is in play, because the two are never
        # equal then.
        return self._raw_catalog != before

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
        require_descriptor_owner(descriptor, self._name)
        require_endpoint(descriptor, endpoint, self._name)
        if endpoint not in _SEND_METHODS:
            raise EndpointNotImplemented(self._name, endpoint.value)
        return await self._client.send(
            endpoint,
            payload,
            stream=stream,
            extra_headers=extra_headers,
            interaction_id=interaction_id,
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
