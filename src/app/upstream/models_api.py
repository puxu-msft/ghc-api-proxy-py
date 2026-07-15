from collections.abc import Mapping
from typing import Any, cast

import httpx

from app.models.common import ModelInfo


class ModelCatalog:
    def __init__(
        self,
        http_client: httpx.AsyncClient | None,
        base_url: str,
        *,
        disabled_ids: set[str] | frozenset[str] = frozenset(),
    ) -> None:
        self._http = http_client
        self._base_url = base_url.rstrip("/")
        self._disabled_ids = frozenset(disabled_ids)
        self._etag: str | None = None
        self._raw: dict[str, Any] = {"object": "list", "data": []}
        self._by_id: dict[str, ModelInfo] = {}
        self._available_ids: frozenset[str] = frozenset()

    @property
    def raw(self) -> Mapping[str, Any]:
        return self._raw

    @property
    def models(self) -> tuple[ModelInfo, ...]:
        return tuple(self._by_id.values())

    @property
    def available_ids(self) -> frozenset[str]:
        return self._available_ids

    def get(self, model_id: str) -> ModelInfo | None:
        return self._by_id.get(model_id)

    def replace_from_data(self, data: Mapping[str, Any]) -> None:
        raw_models_value: object = data.get("data")
        if not isinstance(raw_models_value, list):
            raise ValueError("models response data must be a list")
        raw_models = cast(list[object], raw_models_value)
        models = [ModelInfo.model_validate(model) for model in raw_models]
        by_id = {model.id: model for model in models}
        self._raw = dict(data)
        self._by_id = by_id
        self._available_ids = frozenset(by_id) - self._disabled_ids

    async def refresh(self, headers: Mapping[str, str]) -> bool:
        if self._http is None:
            raise RuntimeError("model catalog has no HTTP client")
        request_headers = dict(headers)
        if self._etag is not None:
            request_headers["If-None-Match"] = self._etag
        response = await self._http.get(f"{self._base_url}/models", headers=request_headers)
        if response.status_code == 304:
            return False
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        self.replace_from_data(data)
        if etag := response.headers.get("etag"):
            self._etag = etag
        return True