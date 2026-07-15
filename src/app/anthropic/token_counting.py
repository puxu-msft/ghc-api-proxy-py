from collections.abc import Mapping
from typing import Any, Protocol

import httpx
import tiktoken
from anyio.to_thread import run_sync

from app.models.anthropic import ContentBlock, MessagesRequest
from app.wire_json import dumps


class CountTokensTarget(Protocol):
    async def send_anthropic_count_tokens(
        self,
        payload: Mapping[str, Any],
    ) -> httpx.Response: ...


def _content_for_count(content: str | list[ContentBlock], *, assistant: bool) -> str:
    if isinstance(content, str):
        return content
    values: list[str] = []
    for block in content:
        if assistant and block.type in ("thinking", "redacted_thinking"):
            continue
        if block.text:
            values.append(block.text)
        elif block.content is not None:
            values.append(str(block.content))
        elif block.input is not None:
            values.append(dumps(block.input).decode())
    return "\n".join(values)


def estimate_input_tokens(request: MessagesRequest) -> int:
    encoding = tiktoken.get_encoding("o200k_base")
    total = 0
    if isinstance(request.system, str):
        total += len(encoding.encode(request.system)) + 4
    elif request.system:
        total += sum(len(encoding.encode(block.text)) + 4 for block in request.system)
    if request.tools:
        tool_data = [tool.model_dump(mode="json", exclude_none=True) for tool in request.tools]
        total += len(encoding.encode(dumps(tool_data).decode())) + 4
    for message in request.messages:
        total += len(encoding.encode(message.role))
        total += len(
            encoding.encode(
                _content_for_count(message.content, assistant=message.role == "assistant")
            )
        )
        total += 4
    return max(total, 1)


class TokenCounter:
    def __init__(
        self,
        target: CountTokensTarget,
        *,
        use_upstream: bool = True,
        offload_threshold_bytes: int = 100_000,
    ) -> None:
        self._target = target
        self._use_upstream = use_upstream
        self._offload_threshold = offload_threshold_bytes

    async def _estimate(self, request: MessagesRequest) -> int:
        wire_size = len(dumps(request.model_dump(mode="json", exclude_none=True)))
        if wire_size >= self._offload_threshold:
            return await run_sync(estimate_input_tokens, request)
        return estimate_input_tokens(request)

    async def count(self, request: MessagesRequest) -> dict[str, Any]:
        if self._use_upstream:
            payload = request.model_dump(mode="json", exclude_none=True)
            payload.pop("stream", None)
            try:
                response = await self._target.send_anthropic_count_tokens(payload)
                response.raise_for_status()
                data: dict[str, Any] = response.json()
                return data
            except (httpx.HTTPError, OSError, ValueError):
                pass
        return {"input_tokens": await self._estimate(request), "estimated": True}