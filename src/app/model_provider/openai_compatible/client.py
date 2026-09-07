"""Raw HTTP client for the sub2api provider."""

from collections.abc import Mapping
from typing import Any, cast

import httpx2

from app.config.schema import OpenAICompatibleProviderConfig
from app.model_provider.openai_compatible.errors import upstream_error_from_response
from app.model_provider.types import ModelEndpoint
from app.model_provider.upstream_errors import normalize_upstream_error
from app.wire_json import dumps

ANTHROPIC_MESSAGES_PATH = "/v1/messages"
COUNT_TOKENS_PATH = "/v1/messages/count_tokens"
RESPONSES_PATH = "/responses"
CHAT_COMPLETIONS_PATH = "/chat/completions"
EMBEDDINGS_PATH = "/embeddings"
MODELS_PATH = "/models"

_PATHS = {
    ModelEndpoint.ANTHROPIC_MESSAGES: ANTHROPIC_MESSAGES_PATH,
    ModelEndpoint.OPENAI_RESPONSES: RESPONSES_PATH,
    ModelEndpoint.OPENAI_CHAT_COMPLETIONS: CHAT_COMPLETIONS_PATH,
    ModelEndpoint.OPENAI_EMBEDDINGS: EMBEDDINGS_PATH,
}
_OWNED_HEADERS = frozenset(
    {
        "accept",
        "authorization",
        "content-type",
        "host",
    }
)


class OpenAICompatibleClient:
    def __init__(
        self,
        http_client: httpx2.AsyncClient,
        config: OpenAICompatibleProviderConfig,
    ) -> None:
        self._http = http_client
        self._config = config
        self._base_url = config.api_base_url.rstrip("/")

    @property
    def base_url(self) -> str:
        return self._base_url

    def _headers(
        self,
        *,
        stream: bool = False,
        extra_headers: Mapping[str, str] | None = None,
    ) -> dict[str, str]:
        headers: dict[str, str] = {
            "Accept": "text/event-stream" if stream else "application/json",
            "Content-Type": "application/json",
        }
        if self._config.api_key:
            headers["Authorization"] = f"Bearer {self._config.api_key}"
        if extra_headers:
            headers.update(
                {
                    str(name): str(value)
                    for name, value in extra_headers.items()
                    if str(name).lower() not in _OWNED_HEADERS
                }
            )
        return headers

    def _anthropic_path(self, path: str) -> str:
        if self._base_url.endswith("/v1"):
            return path.removeprefix("/v1")
        return path

    async def _send(
        self,
        request: httpx2.Request,
        *,
        stream: bool,
    ) -> httpx2.Response:
        try:
            response = await self._http.send(request, stream=stream)
        except BaseException as error:
            normalized = normalize_upstream_error(error)
            if normalized is None:
                raise
            raise normalized from error
        if response.is_success:
            return response
        try:
            if not response.is_stream_consumed:
                await response.aread()
            raise upstream_error_from_response(response)
        finally:
            await response.aclose()

    async def send(
        self,
        endpoint: ModelEndpoint,
        payload: Mapping[str, Any],
        *,
        stream: bool = False,
        extra_headers: Mapping[str, str] | None = None,
    ) -> httpx2.Response:
        path = _PATHS[endpoint]
        if endpoint is ModelEndpoint.ANTHROPIC_MESSAGES:
            path = self._anthropic_path(path)
        body = dumps(dict(payload))
        request = self._http.build_request(
            "POST",
            f"{self._base_url}{path}",
            headers=self._headers(stream=stream, extra_headers=extra_headers),
            content=body,
        )
        return await self._send(request, stream=stream)

    async def fetch_models(self) -> dict[str, Any]:
        response = await self._http.get(
            f"{self._base_url}{MODELS_PATH}",
            headers=self._headers(),
        )
        if not response.is_success:
            try:
                raise upstream_error_from_response(response)
            finally:
                await response.aclose()
        try:
            loaded = cast(object, response.json())
        finally:
            await response.aclose()
        if not isinstance(loaded, dict):
            raise ValueError("OpenAI-compatible models response must be an object")
        return cast(dict[str, Any], loaded)

    async def count_tokens(self, payload: Mapping[str, Any]) -> httpx2.Response:
        body = dumps(dict(payload))
        request = self._http.build_request(
            "POST",
            f"{self._base_url}{self._anthropic_path(COUNT_TOKENS_PATH)}",
            headers=self._headers(),
            content=body,
        )
        return await self._send(request, stream=False)
