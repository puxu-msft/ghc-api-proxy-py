from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

import httpx2

from app.config.schema import XingchenProviderConfig
from app.model_provider.types import (
    CatalogSnapshot,
    ModelDescriptor,
    ModelEndpoint,
    require_descriptor_owner,
    require_endpoint,
)
from app.model_provider.xingchen.client import XingchenClient

PROVIDER_TYPE = "xingchen"
DRIVEN_ENDPOINTS = frozenset({ModelEndpoint.OPENAI_CHAT_COMPLETIONS})


class XingchenProvider:
    def __init__(
        self,
        name: str,
        client: XingchenClient,
        config: XingchenProviderConfig,
    ) -> None:
        self._name = name
        self._client = client
        self._disabled = frozenset(config.disabled_models)
        self._catalog_generation = 1
        self._refreshed_at = datetime.now(UTC).isoformat(timespec="seconds")
        self._descriptors = {
            model_id: ModelDescriptor(
                id=model_id,
                endpoints=DRIVEN_ENDPOINTS,
                provider_name=self._name,
                catalog_generation=self._catalog_generation,
                catalog_refreshed_at=self._refreshed_at,
            )
            for model_id in config.models
        }
        self._raw_catalog: dict[str, Any] = {
            "object": "list",
            "data": [
                {
                    "id": model_id,
                    "object": "model",
                    "supported_endpoints": [ModelEndpoint.OPENAI_CHAT_COMPLETIONS.value],
                    "capabilities": {"type": "chat"},
                }
                for model_id in config.models
            ],
        }

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
        """The catalog exactly as this provider publishes it — static, like the protocol docstring says."""
        return self._raw_catalog

    @property
    def catalog_snapshot(self) -> CatalogSnapshot:
        return CatalogSnapshot(
            raw=self._raw_catalog,
            source="static",
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

    async def refresh_catalog(self) -> bool:
        return False

    async def send(
        self,
        endpoint: ModelEndpoint,
        payload: Mapping[str, Any],
        *,
        descriptor: ModelDescriptor,
        stream: bool = False,
        extra_headers: Mapping[str, str] | None = None,
    ) -> httpx2.Response:
        require_descriptor_owner(descriptor, self._name)
        require_endpoint(descriptor, endpoint, self._name)
        return await self._client.send_chat_completions(
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
        del payload
        require_descriptor_owner(descriptor, self._name)
        require_endpoint(descriptor, ModelEndpoint.ANTHROPIC_MESSAGES, self._name)
        raise AssertionError("Xingchen descriptors must never advertise Anthropic Messages")
