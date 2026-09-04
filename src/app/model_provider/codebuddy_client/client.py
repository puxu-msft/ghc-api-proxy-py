"""Sends requests to the CodeBuddy backend.

One inference endpoint, `/v2/chat/completions`, spoken with the desktop login state's
headers. The upstream answers only streaming requests — measured by the reference
converter, which always sends `stream: true` and aggregates for non-streaming
clients — so this client forces streaming on the wire and, when the caller asked for
a non-streaming response, aggregates the SSE into a single `chat.completion` body
here. That keeps the aggregation on the provider side of the `ModelProvider` seam:
the pipeline asks for stream or not, and how the upstream is persuaded to answer is
this library's business.
"""

import time
import uuid
from collections.abc import Mapping
from typing import Any, cast

import httpx2
import orjson

from app.model_provider.codebuddy_client.auth_state import CodebuddyCredentials
from app.model_provider.codebuddy_client.config import CodebuddyClientConfig
from app.model_provider.codebuddy_client.errors import upstream_error_from
from app.pipeline.exceptions import UpstreamError, UpstreamTimeout

CHAT_COMPLETIONS_PATH = "/v2/chat/completions"


class CodebuddyClient:
    def __init__(
        self,
        config: CodebuddyClientConfig,
        credentials: CodebuddyCredentials,
        *,
        http_client: httpx2.AsyncClient,
    ) -> None:
        self._config = config
        self._credentials = credentials
        self._http = http_client

    @property
    def api_base_url(self) -> str:
        return self._config.api_base_url

    async def request_headers(
        self, *, extra_headers: Mapping[str, str] | None = None
    ) -> dict[str, str]:
        return await self._credentials.request_headers(extra_headers=dict(extra_headers or {}))

    async def send_chat_completions(
        self,
        payload: Mapping[str, Any],
        *,
        stream: bool = False,
    ) -> httpx2.Response:
        body = dict(payload)
        # The upstream has no non-streaming mode (measured by the reference, which
        # never sends `stream: false`), so the wire always streams; a caller that
        # asked for one body gets the aggregation below.
        body["stream"] = True
        if "stream_options" not in body:
            # Usage rides the final chunk only when asked for; without it a
            # non-streaming reply and a streaming terminal both report nothing.
            body["stream_options"] = {"include_usage": True}
        headers = await self._credentials.request_headers()
        url = f"{self._config.api_base_url}{CHAT_COMPLETIONS_PATH}"
        # `send(stream=True)` rather than `post`: the post helper reads the whole body
        # before returning, which would turn a streamed reply into a buffered one and
        # defeat the delivery layer entirely.
        request = self._http.build_request("POST", url, headers=headers, json=body)
        try:
            response = await self._http.send(request, stream=True)
        except httpx2.TimeoutException as error:
            raise UpstreamTimeout(f"upstream timed out: {error}") from error
        except httpx2.HTTPError as error:
            raise UpstreamError(f"upstream connection failed: {error}") from error
        if response.status_code != 200:
            # Read before classifying: the classifier reads `response.text`, which
            # raises on a response whose body was never pulled.
            await response.aread()
            raise upstream_error_from(response)
        if stream:
            return response
        try:
            return await aggregate_stream(response)
        finally:
            await response.aclose()


async def aggregate_stream(response: httpx2.Response) -> httpx2.Response:
    """Consume an upstream SSE body and answer one `chat.completion` object.

    The chunk vocabulary is standard OpenAI: `choices[].delta` accumulates `content`
    and index-keyed `tool_calls`, `finish_reason` arrives on a choice, `usage` rides
    a final chunk. Mirrors the reference converter's `_collect_stream`, including the
    detail that a reply made of tool calls with no explicit `finish_reason` still
    finishes as `tool_calls`.
    """
    content_parts: list[str] = []
    tool_calls: dict[int, dict[str, Any]] = {}
    model = ""
    finish_reason = ""
    usage: dict[str, Any] = {}

    async for line in response.aiter_lines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            break
        try:
            loaded = cast(object, orjson.loads(data))
        except ValueError:
            continue
        if not isinstance(loaded, dict):
            continue
        chunk = cast(dict[str, Any], loaded)
        if isinstance(chunk.get("model"), str) and chunk["model"]:
            model = chunk["model"]
        if isinstance(chunk.get("usage"), dict):
            usage = cast(dict[str, Any], chunk["usage"])
        choices = chunk.get("choices")
        if not isinstance(choices, list):
            continue
        for choice in cast(list[object], choices):
            if not isinstance(choice, dict):
                continue
            one = cast(dict[str, Any], choice)
            if isinstance(one.get("finish_reason"), str) and one["finish_reason"]:
                finish_reason = one["finish_reason"]
            delta = one.get("delta")
            if not isinstance(delta, dict):
                continue
            deltas = cast(dict[str, Any], delta)
            if isinstance(deltas.get("content"), str):
                content_parts.append(deltas["content"])
            raw_calls = deltas.get("tool_calls")
            if not isinstance(raw_calls, list):
                continue
            for call in cast(list[object], raw_calls):
                if not isinstance(call, dict):
                    continue
                call_dict = cast(dict[str, Any], call)
                index = call_dict.get("index", 0)
                if not isinstance(index, int) or isinstance(index, bool):
                    index = 0
                slot = tool_calls.setdefault(index, {"id": "", "name": "", "arguments": ""})
                if isinstance(call_dict.get("id"), str) and call_dict["id"]:
                    slot["id"] = call_dict["id"]
                function = call_dict.get("function")
                if not isinstance(function, dict):
                    continue
                function_dict = cast(dict[str, Any], function)
                if isinstance(function_dict.get("name"), str) and function_dict["name"]:
                    slot["name"] = function_dict["name"]
                if isinstance(function_dict.get("arguments"), str):
                    slot["arguments"] += function_dict["arguments"]

    message: dict[str, Any] = {"role": "assistant", "content": "".join(content_parts) or None}
    if tool_calls:
        message["tool_calls"] = [
            {
                "id": slot["id"],
                "type": "function",
                "function": {"name": slot["name"], "arguments": slot["arguments"]},
            }
            for _, slot in sorted(tool_calls.items())
        ]
        finish_reason = finish_reason or "tool_calls"
    body = {
        "id": f"chatcmpl-{uuid.uuid4().hex}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model or "unknown",
        "choices": [
            {
                "index": 0,
                "message": message,
                "finish_reason": finish_reason or "stop",
            }
        ],
    }
    if usage:
        body["usage"] = usage
    return httpx2.Response(
        200,
        content=orjson.dumps(body),
        headers={"content-type": "application/json"},
        request=response.request,
    )
