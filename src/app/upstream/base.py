from collections.abc import Mapping
from typing import Any, Protocol

import httpx
from openai import APIConnectionError as OpenAIAPIConnectionError

_RESPONSES_PRE_HEADERS_HTTPX_ERRORS = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.PoolTimeout,
)


class ResponsesHeadersPendingTransportError(Exception):
    def __init__(self, original: Exception) -> None:
        super().__init__(str(original))
        self.original = original


def is_responses_headers_pending_transport_error(error: Exception) -> bool:
    if isinstance(error, _RESPONSES_PRE_HEADERS_HTTPX_ERRORS):
        return True
    if not isinstance(error, OpenAIAPIConnectionError):
        return False
    cause = error.__cause__
    if cause is None:
        return False
    while cause is not None:
        if isinstance(cause, httpx.TransportError):
            return isinstance(cause, _RESPONSES_PRE_HEADERS_HTTPX_ERRORS)
        cause = cause.__cause__
    return False


class UpstreamTarget(Protocol):
    async def send_openai(
        self,
        payload: Mapping[str, Any],
        *,
        stream: bool = False,
    ) -> httpx.Response: ...

    async def send_anthropic(
        self,
        payload: Mapping[str, Any],
        *,
        stream: bool = False,
        extra_headers: Mapping[str, str] | None = None,
    ) -> httpx.Response: ...

    async def send_anthropic_count_tokens(
        self,
        payload: Mapping[str, Any],
    ) -> httpx.Response: ...

    async def send_responses(
        self,
        payload: Mapping[str, Any],
        *,
        stream: bool = False,
    ) -> httpx.Response: ...

    async def send_responses_headers(
        self,
        payload: Mapping[str, Any],
    ) -> httpx.Response: ...

    async def send_embeddings(
        self,
        payload: Mapping[str, Any],
    ) -> httpx.Response: ...