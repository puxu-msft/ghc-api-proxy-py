from collections.abc import Mapping
from typing import Any, Protocol

import httpx


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
    ) -> httpx.Response: ...

    async def send_responses(
        self,
        payload: Mapping[str, Any],
        *,
        stream: bool = False,
    ) -> httpx.Response: ...