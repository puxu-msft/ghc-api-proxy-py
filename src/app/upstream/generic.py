from collections.abc import Mapping
from typing import Any, cast

import httpx
from anthropic._types import Body as AnthropicBody
from openai import (
    APIConnectionError as OpenAIAPIConnectionError,
)
from openai import (
    APIStatusError as OpenAIAPIStatusError,
)
from openai._types import Body as OpenAIBody

from app.upstream.base import (
    ResponsesHeadersPendingTransportError,
    is_responses_headers_pending_transport_error,
)
from app.upstream.client import SDKClients


class GenericUpstream:
    def __init__(self, clients: SDKClients) -> None:
        self._clients = clients

    async def send_openai(
        self,
        payload: Mapping[str, Any],
        *,
        stream: bool = False,
    ) -> httpx.Response:
        return await self._clients.openai.post(
            "/chat/completions",
            cast_to=httpx.Response,
            body=cast(OpenAIBody, dict(payload)),
            stream=stream,
        )

    async def send_anthropic(
        self,
        payload: Mapping[str, Any],
        *,
        stream: bool = False,
        extra_headers: Mapping[str, str] | None = None,
    ) -> httpx.Response:
        return await self._clients.anthropic.post(
            "/v1/messages",
            cast_to=httpx.Response,
            body=cast(AnthropicBody, dict(payload)),
            options={"headers": dict(extra_headers or {})},
            stream=stream,
        )

    async def send_anthropic_count_tokens(
        self,
        payload: Mapping[str, Any],
    ) -> httpx.Response:
        return await self._clients.anthropic.post(
            "/v1/messages/count_tokens",
            cast_to=httpx.Response,
            body=cast(AnthropicBody, dict(payload)),
        )

    async def send_responses(
        self,
        payload: Mapping[str, Any],
        *,
        stream: bool = False,
    ) -> httpx.Response:
        return await self._clients.openai.post(
            "/responses",
            cast_to=httpx.Response,
            body=cast(OpenAIBody, dict(payload)),
            stream=stream,
        )

    async def send_responses_headers(
        self,
        payload: Mapping[str, Any],
    ) -> httpx.Response:
        try:
            return await self._clients.openai.post(
                "/responses",
                cast_to=httpx.Response,
                body=cast(OpenAIBody, dict(payload)),
                stream=True,
            )
        except OpenAIAPIStatusError as error:
            return error.response
        except (httpx.TransportError, OpenAIAPIConnectionError) as error:
            if is_responses_headers_pending_transport_error(error):
                raise ResponsesHeadersPendingTransportError(error) from error
            raise

    async def send_embeddings(
        self,
        payload: Mapping[str, Any],
    ) -> httpx.Response:
        return await self._clients.openai.post(
            "/embeddings",
            cast_to=httpx.Response,
            body=cast(OpenAIBody, dict(payload)),
        )