from collections.abc import Mapping
from typing import Any, Protocol

import httpx

from app.ghc_client.transport import (
    ResponsesHeadersPendingTransportError,
    is_responses_headers_pending_transport_error,
)

__all__ = [
    "ResponsesHeadersPendingTransportError",
    "UpstreamTarget",
    "is_responses_headers_pending_transport_error",
]


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
