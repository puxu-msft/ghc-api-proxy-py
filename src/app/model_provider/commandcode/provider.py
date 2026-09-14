"""The Command Code provider, which drives its native generation protocol."""

import logging
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, cast

import httpx2

from app.config.schema import CommandCodeProviderConfig
from app.model_provider.commandcode.client import CommandCodeClient
from app.model_provider.types import (
    CatalogSnapshot,
    CatalogSource,
    EndpointNotImplemented,
    ModelDescriptor,
    ModelEndpoint,
    require_descriptor_owner,
    require_endpoint,
)

PROVIDER_TYPE = "commandcode"
DRIVEN_ENDPOINTS = frozenset({ModelEndpoint.COMMANDCODE_GENERATE})
logger = logging.getLogger(__name__)


class CommandCodeProvider:
    def __init__(
        self,
        name: str,
        client: CommandCodeClient,
        config: CommandCodeProviderConfig,
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
        if config.models:
            self.replace_catalog(
                {
                    "object": "list",
                    "data": [{"id": model_id} for model_id in config.models],
                },
                source="static",
            )

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
            raise ValueError("Command Code models response data must be a list")
        generation = self._catalog_generation + 1
        refreshed_at = datetime.now(UTC).isoformat(timespec="seconds")
        allowed = frozenset(self._config.models)
        descriptors: dict[str, ModelDescriptor] = {}
        for entry in cast(list[Any], entries):
            if not isinstance(entry, dict):
                continue
            model = cast(dict[str, Any], entry)
            model_id = model.get("id")
            if not isinstance(model_id, str) or not model_id:
                continue
            if allowed and model_id not in allowed:
                continue
            descriptors[model_id] = ModelDescriptor(
                id=model_id,
                endpoints=DRIVEN_ENDPOINTS,
                provider_name=self._name,
                catalog_generation=generation,
                catalog_refreshed_at=refreshed_at,
            )
        self._descriptors = descriptors
        self._raw_catalog = dict(raw)
        self._catalog_source = source
        self._catalog_generation = generation
        self._refreshed_at = refreshed_at

    async def refresh_catalog(self) -> bool:
        try:
            raw = await self._client.fetch_models()
            before = self._raw_catalog
            self.replace_catalog(raw)
        except Exception as error:
            if self._config.models:
                logger.warning(
                    "Command Code catalog refresh failed; retaining configured static catalog: %s",
                    error,
                )
                return False
            raise
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
        require_descriptor_owner(descriptor, self._name)
        require_endpoint(descriptor, endpoint, self._name)
        if endpoint is not ModelEndpoint.COMMANDCODE_GENERATE:
            raise EndpointNotImplemented(self._name, endpoint.value)
        return await self._client.send(
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
        del payload
        require_descriptor_owner(descriptor, self._name)
        raise EndpointNotImplemented(self._name, "count_tokens")
