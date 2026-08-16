"""GitHub Copilot as a model provider, backed by the `app.ghc_client` library."""

from collections.abc import Mapping
from typing import Any, cast

import httpx

from app.config.schema import ModelProviderConfig
from app.ghc_client import GhcApiClient, fetch_models
from app.model_provider.types import (
    EndpointNotImplemented,
    ModelDescriptor,
    ModelEndpoint,
    UnknownModel,
    parse_endpoints,
    require_endpoint,
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


class GithubCopilotProvider:
    def __init__(
        self,
        name: str,
        client: GhcApiClient,
        config: ModelProviderConfig,
        *,
        http_client: httpx.AsyncClient,
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
        self._etag: str | None = None

    @property
    def name(self) -> str:
        return self._name

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
            known, unknown = parse_endpoints(model.get("supported_endpoints"))
            descriptors[model_id] = ModelDescriptor(
                id=model_id,
                endpoints=known,
                unknown_endpoints=unknown,
                request_headers=_string_mapping(model.get("request_headers")),
            )
        self._descriptors = descriptors

    async def refresh_catalog(self) -> bool:
        page = await fetch_models(
            self._http,
            self._base_url,
            self._catalog_headers,
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
    ) -> httpx.Response:
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
            return await self._client.send_chat_completions(payload, stream=stream)
        if endpoint is ModelEndpoint.OPENAI_RESPONSES:
            return await self._client.send_responses(payload, stream=stream)
        return await self._client.send_embeddings(payload)

    async def count_tokens(
        self,
        payload: Mapping[str, Any],
        *,
        model_id: str,
    ) -> httpx.Response:
        """Anthropic token counting.

        The spec groups it with the Messages driver rather than giving it its own routing row.
        It is therefore gated on the Messages capability.
        """
        descriptor = self.describe(model_id)
        if descriptor is None:
            raise UnknownModel(self._name, model_id)
        require_endpoint(descriptor, ModelEndpoint.ANTHROPIC_MESSAGES, self._name)
        return await self._client.send_anthropic_count_tokens(payload)
